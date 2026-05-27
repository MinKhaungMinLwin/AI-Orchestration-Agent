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
        smrt_pay_yn (None | str | Unset): 스마트페이 가능 여부 Y/N (활성 PR_ITEM_PRC_INFO.SMRT_PAY_PRC > 0 기준)
        image_url (None | str | Unset): 대표 이미지 URL (PR_PTRN_IMG_INFO IMG_SCT_CD='80' + IMAGE_BASE_URL)
        label_pnwave (None | str | Unset): EU 소음 라벨 등급 코드 (LABEL_PNWAVE). 값: 'AA'(최저소음) / 'A'(저소음) / 그 외
        label_pnwave_nm (None | str | Unset): EU 소음 라벨 등급명 (DECODE(LABEL_PNWAVE)): '최저소음' / '저소음' / ''
        label_pndb (None | str | Unset): EU 소음 데시벨 라벨 값 (LABEL_PNDB, VARCHAR2)
        prc_grd_nm (None | str | Unset): 가격 등급명 (PR_GOODS_BASE.PRC_GRD_NM). 응답값: '프리미엄' (DB 원본 '프리미엄+' 도 응답 단계에서 '프리미엄'
            으로 정규화) / '스탠다드' / '이코노미'. 표시·답변용 — 검색 정렬/필터 기준 아님
        goods_pfm_nm (None | str | Unset): 퍼포먼스 분류명 (PR_GOODS_BASE.GOODS_PFM_NM). 값 매핑: 'COMFORT'(정숙/승차감) /
            'SPORT'(고속/제동성) / 'RUNFLAT'(런플랫) 등. 표시·답변용 — 검색 정렬/필터 기준 아님
        t_oe_maker_1 (None | str | Unset): OE 메이커 코드/명 (PR_GOODS_BASE.T_OE_MAKER_1)
        oe_badge_yn (None | str | Unset): OE 뱃지 노출 여부. T_OE_MAKER_1 값이 있으면 Y, 없으면 N
        sale_prc (int | None | Unset): 기본 판매가 (PR_ITEM_PRC_INFO.SALE_PRC)
        extra_fvr_sale_prc (int | None | Unset): 최대 혜택 판매가. 회원 유형에 따라 PR_GOODS_DSCNT_PRC_INFO(일반) 또는
            PR_GOODS_ENTR_DSCNT_PRC_INFO(PARTNER)에서 join
        extra_fvr_sale_per (float | None | Unset): 최대 혜택 할인율 (%)
        sys_reg_dtime (None | str | Unset): 상품 등록 일시 (PR_GOODS_BASE.SYS_REG_DTIME, 형식: 'YYYY-MM-DD HH24:MI:SS')
        big_goods_nm (None | str | Unset): 대상품명 (BIG_GOODS_NM)
        ptrn_d_nm (None | str | Unset): 직관적 명칭 (PTRN_D_NM)
        tire_width (None | str | Unset): 단면폭 (TIRE_WIDTH)
        tire_series (None | str | Unset): 편평비 (TIRE_SERIES)
        inch (None | str | Unset): 인치 (INCH)
        t_wgt_idx (None | str | Unset): 하중지수 (T_WGT_IDX)
        t_wgt_idx_kg (None | str | Unset): 하중지수KG (T_WGT_IDX_KG)
        t_wgt_spd (None | str | Unset): 하중·속도 (T_WGT_SPD)
        t_highspd (None | str | Unset): 최대속도 (T_HIGHSPD)
        season_nm (None | str | Unset): 계절 속성 (SEASON_NM)
        car_knd_nm (None | str | Unset): 차종 속성 (CAR_KND_NM)
        brand_nm (None | str | Unset): 브랜드명 (BRAND_NM)
        certify_brand_nm (None | str | Unset): 공식인증 브랜드명 (CERTIFY_BRAND_NM)
        orpl_nm (None | str | Unset): 원산지명 (ORPL_NM)
        t_rls_yearmon (None | str | Unset): 출시년월 (T_RLS_YEARMON)
        t_comfort (None | str | Unset): 승차감 (T_COMFORT)
        t_silence (None | str | Unset): 정숙성 (T_SILENCE)
        t_high_perform (None | str | Unset): 고속주행성능 (T_HIGH_PERFORM)
        t_handling (None | str | Unset): 핸들링 (T_HANDLING)
        t_life_span (None | str | Unset): 타이어수명 (T_LIFE_SPAN)
        t_snow (None | str | Unset): SNOW 제동력 (T_SNOW)
        t_ice (None | str | Unset): ICE 제동력 (T_ICE)
        t_dryroad_brk (None | str | Unset): 마른노면 제동력 (T_DRYROAD_BRK)
        rr (None | str | Unset): 회전저항 등급 (RR)
        wet (None | str | Unset): 젖은노면 제동 등급 (WET)
        wage_prc (int | None | Unset): 공임비 (WAGE_PRC)
        wage_today_prc (int | None | Unset): 오늘공임비 (WAGE_TODAY_PRC)
        free_guarantee_yn (None | str | Unset): 무상교환보증 여부 Y/N (FREE_GUARANTEE_YN)
        t_rlx_isn_yn (None | str | Unset): 안심보험 여부 Y/N (T_RLX_ISN_YN)
    """

    goods_no: str
    goods_nm: str
    tire_size_1: None | str | Unset = UNSET
    tire_size_2: None | str | Unset = UNSET
    score: int | Unset = 0
    match_type: str | Unset = "none"
    smrt_pay_yn: None | str | Unset = UNSET
    image_url: None | str | Unset = UNSET
    label_pnwave: None | str | Unset = UNSET
    label_pnwave_nm: None | str | Unset = UNSET
    label_pndb: None | str | Unset = UNSET
    prc_grd_nm: None | str | Unset = UNSET
    goods_pfm_nm: None | str | Unset = UNSET
    t_oe_maker_1: None | str | Unset = UNSET
    oe_badge_yn: None | str | Unset = UNSET
    sale_prc: int | None | Unset = UNSET
    extra_fvr_sale_prc: int | None | Unset = UNSET
    extra_fvr_sale_per: float | None | Unset = UNSET
    sys_reg_dtime: None | str | Unset = UNSET
    big_goods_nm: None | str | Unset = UNSET
    ptrn_d_nm: None | str | Unset = UNSET
    tire_width: None | str | Unset = UNSET
    tire_series: None | str | Unset = UNSET
    inch: None | str | Unset = UNSET
    t_wgt_idx: None | str | Unset = UNSET
    t_wgt_idx_kg: None | str | Unset = UNSET
    t_wgt_spd: None | str | Unset = UNSET
    t_highspd: None | str | Unset = UNSET
    season_nm: None | str | Unset = UNSET
    car_knd_nm: None | str | Unset = UNSET
    brand_nm: None | str | Unset = UNSET
    certify_brand_nm: None | str | Unset = UNSET
    orpl_nm: None | str | Unset = UNSET
    t_rls_yearmon: None | str | Unset = UNSET
    t_comfort: None | str | Unset = UNSET
    t_silence: None | str | Unset = UNSET
    t_high_perform: None | str | Unset = UNSET
    t_handling: None | str | Unset = UNSET
    t_life_span: None | str | Unset = UNSET
    t_snow: None | str | Unset = UNSET
    t_ice: None | str | Unset = UNSET
    t_dryroad_brk: None | str | Unset = UNSET
    rr: None | str | Unset = UNSET
    wet: None | str | Unset = UNSET
    wage_prc: int | None | Unset = UNSET
    wage_today_prc: int | None | Unset = UNSET
    free_guarantee_yn: None | str | Unset = UNSET
    t_rlx_isn_yn: None | str | Unset = UNSET
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

        sys_reg_dtime: None | str | Unset
        if isinstance(self.sys_reg_dtime, Unset):
            sys_reg_dtime = UNSET
        else:
            sys_reg_dtime = self.sys_reg_dtime

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

        tire_width: None | str | Unset
        if isinstance(self.tire_width, Unset):
            tire_width = UNSET
        else:
            tire_width = self.tire_width

        tire_series: None | str | Unset
        if isinstance(self.tire_series, Unset):
            tire_series = UNSET
        else:
            tire_series = self.tire_series

        inch: None | str | Unset
        if isinstance(self.inch, Unset):
            inch = UNSET
        else:
            inch = self.inch

        t_wgt_idx: None | str | Unset
        if isinstance(self.t_wgt_idx, Unset):
            t_wgt_idx = UNSET
        else:
            t_wgt_idx = self.t_wgt_idx

        t_wgt_idx_kg: None | str | Unset
        if isinstance(self.t_wgt_idx_kg, Unset):
            t_wgt_idx_kg = UNSET
        else:
            t_wgt_idx_kg = self.t_wgt_idx_kg

        t_wgt_spd: None | str | Unset
        if isinstance(self.t_wgt_spd, Unset):
            t_wgt_spd = UNSET
        else:
            t_wgt_spd = self.t_wgt_spd

        t_highspd: None | str | Unset
        if isinstance(self.t_highspd, Unset):
            t_highspd = UNSET
        else:
            t_highspd = self.t_highspd

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

        t_comfort: None | str | Unset
        if isinstance(self.t_comfort, Unset):
            t_comfort = UNSET
        else:
            t_comfort = self.t_comfort

        t_silence: None | str | Unset
        if isinstance(self.t_silence, Unset):
            t_silence = UNSET
        else:
            t_silence = self.t_silence

        t_high_perform: None | str | Unset
        if isinstance(self.t_high_perform, Unset):
            t_high_perform = UNSET
        else:
            t_high_perform = self.t_high_perform

        t_handling: None | str | Unset
        if isinstance(self.t_handling, Unset):
            t_handling = UNSET
        else:
            t_handling = self.t_handling

        t_life_span: None | str | Unset
        if isinstance(self.t_life_span, Unset):
            t_life_span = UNSET
        else:
            t_life_span = self.t_life_span

        t_snow: None | str | Unset
        if isinstance(self.t_snow, Unset):
            t_snow = UNSET
        else:
            t_snow = self.t_snow

        t_ice: None | str | Unset
        if isinstance(self.t_ice, Unset):
            t_ice = UNSET
        else:
            t_ice = self.t_ice

        t_dryroad_brk: None | str | Unset
        if isinstance(self.t_dryroad_brk, Unset):
            t_dryroad_brk = UNSET
        else:
            t_dryroad_brk = self.t_dryroad_brk

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

        wage_prc: int | None | Unset
        if isinstance(self.wage_prc, Unset):
            wage_prc = UNSET
        else:
            wage_prc = self.wage_prc

        wage_today_prc: int | None | Unset
        if isinstance(self.wage_today_prc, Unset):
            wage_today_prc = UNSET
        else:
            wage_today_prc = self.wage_today_prc

        free_guarantee_yn: None | str | Unset
        if isinstance(self.free_guarantee_yn, Unset):
            free_guarantee_yn = UNSET
        else:
            free_guarantee_yn = self.free_guarantee_yn

        t_rlx_isn_yn: None | str | Unset
        if isinstance(self.t_rlx_isn_yn, Unset):
            t_rlx_isn_yn = UNSET
        else:
            t_rlx_isn_yn = self.t_rlx_isn_yn

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
        if sale_prc is not UNSET:
            field_dict["sale_prc"] = sale_prc
        if extra_fvr_sale_prc is not UNSET:
            field_dict["extra_fvr_sale_prc"] = extra_fvr_sale_prc
        if extra_fvr_sale_per is not UNSET:
            field_dict["extra_fvr_sale_per"] = extra_fvr_sale_per
        if sys_reg_dtime is not UNSET:
            field_dict["sys_reg_dtime"] = sys_reg_dtime
        if big_goods_nm is not UNSET:
            field_dict["big_goods_nm"] = big_goods_nm
        if ptrn_d_nm is not UNSET:
            field_dict["ptrn_d_nm"] = ptrn_d_nm
        if tire_width is not UNSET:
            field_dict["tire_width"] = tire_width
        if tire_series is not UNSET:
            field_dict["tire_series"] = tire_series
        if inch is not UNSET:
            field_dict["inch"] = inch
        if t_wgt_idx is not UNSET:
            field_dict["t_wgt_idx"] = t_wgt_idx
        if t_wgt_idx_kg is not UNSET:
            field_dict["t_wgt_idx_kg"] = t_wgt_idx_kg
        if t_wgt_spd is not UNSET:
            field_dict["t_wgt_spd"] = t_wgt_spd
        if t_highspd is not UNSET:
            field_dict["t_highspd"] = t_highspd
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
        if t_comfort is not UNSET:
            field_dict["t_comfort"] = t_comfort
        if t_silence is not UNSET:
            field_dict["t_silence"] = t_silence
        if t_high_perform is not UNSET:
            field_dict["t_high_perform"] = t_high_perform
        if t_handling is not UNSET:
            field_dict["t_handling"] = t_handling
        if t_life_span is not UNSET:
            field_dict["t_life_span"] = t_life_span
        if t_snow is not UNSET:
            field_dict["t_snow"] = t_snow
        if t_ice is not UNSET:
            field_dict["t_ice"] = t_ice
        if t_dryroad_brk is not UNSET:
            field_dict["t_dryroad_brk"] = t_dryroad_brk
        if rr is not UNSET:
            field_dict["rr"] = rr
        if wet is not UNSET:
            field_dict["wet"] = wet
        if wage_prc is not UNSET:
            field_dict["wage_prc"] = wage_prc
        if wage_today_prc is not UNSET:
            field_dict["wage_today_prc"] = wage_today_prc
        if free_guarantee_yn is not UNSET:
            field_dict["free_guarantee_yn"] = free_guarantee_yn
        if t_rlx_isn_yn is not UNSET:
            field_dict["t_rlx_isn_yn"] = t_rlx_isn_yn

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

        def _parse_sys_reg_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sys_reg_dtime = _parse_sys_reg_dtime(d.pop("sys_reg_dtime", UNSET))

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

        def _parse_tire_width(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tire_width = _parse_tire_width(d.pop("tire_width", UNSET))

        def _parse_tire_series(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tire_series = _parse_tire_series(d.pop("tire_series", UNSET))

        def _parse_inch(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        inch = _parse_inch(d.pop("inch", UNSET))

        def _parse_t_wgt_idx(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_wgt_idx = _parse_t_wgt_idx(d.pop("t_wgt_idx", UNSET))

        def _parse_t_wgt_idx_kg(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_wgt_idx_kg = _parse_t_wgt_idx_kg(d.pop("t_wgt_idx_kg", UNSET))

        def _parse_t_wgt_spd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_wgt_spd = _parse_t_wgt_spd(d.pop("t_wgt_spd", UNSET))

        def _parse_t_highspd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_highspd = _parse_t_highspd(d.pop("t_highspd", UNSET))

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

        def _parse_t_comfort(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_comfort = _parse_t_comfort(d.pop("t_comfort", UNSET))

        def _parse_t_silence(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_silence = _parse_t_silence(d.pop("t_silence", UNSET))

        def _parse_t_high_perform(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_high_perform = _parse_t_high_perform(d.pop("t_high_perform", UNSET))

        def _parse_t_handling(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_handling = _parse_t_handling(d.pop("t_handling", UNSET))

        def _parse_t_life_span(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_life_span = _parse_t_life_span(d.pop("t_life_span", UNSET))

        def _parse_t_snow(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_snow = _parse_t_snow(d.pop("t_snow", UNSET))

        def _parse_t_ice(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_ice = _parse_t_ice(d.pop("t_ice", UNSET))

        def _parse_t_dryroad_brk(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_dryroad_brk = _parse_t_dryroad_brk(d.pop("t_dryroad_brk", UNSET))

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

        def _parse_wage_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        wage_prc = _parse_wage_prc(d.pop("wage_prc", UNSET))

        def _parse_wage_today_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        wage_today_prc = _parse_wage_today_prc(d.pop("wage_today_prc", UNSET))

        def _parse_free_guarantee_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        free_guarantee_yn = _parse_free_guarantee_yn(d.pop("free_guarantee_yn", UNSET))

        def _parse_t_rlx_isn_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_rlx_isn_yn = _parse_t_rlx_isn_yn(d.pop("t_rlx_isn_yn", UNSET))

        product_search_item = cls(
            goods_no=goods_no,
            goods_nm=goods_nm,
            tire_size_1=tire_size_1,
            tire_size_2=tire_size_2,
            score=score,
            match_type=match_type,
            smrt_pay_yn=smrt_pay_yn,
            image_url=image_url,
            label_pnwave=label_pnwave,
            label_pnwave_nm=label_pnwave_nm,
            label_pndb=label_pndb,
            prc_grd_nm=prc_grd_nm,
            goods_pfm_nm=goods_pfm_nm,
            t_oe_maker_1=t_oe_maker_1,
            oe_badge_yn=oe_badge_yn,
            sale_prc=sale_prc,
            extra_fvr_sale_prc=extra_fvr_sale_prc,
            extra_fvr_sale_per=extra_fvr_sale_per,
            sys_reg_dtime=sys_reg_dtime,
            big_goods_nm=big_goods_nm,
            ptrn_d_nm=ptrn_d_nm,
            tire_width=tire_width,
            tire_series=tire_series,
            inch=inch,
            t_wgt_idx=t_wgt_idx,
            t_wgt_idx_kg=t_wgt_idx_kg,
            t_wgt_spd=t_wgt_spd,
            t_highspd=t_highspd,
            season_nm=season_nm,
            car_knd_nm=car_knd_nm,
            brand_nm=brand_nm,
            certify_brand_nm=certify_brand_nm,
            orpl_nm=orpl_nm,
            t_rls_yearmon=t_rls_yearmon,
            t_comfort=t_comfort,
            t_silence=t_silence,
            t_high_perform=t_high_perform,
            t_handling=t_handling,
            t_life_span=t_life_span,
            t_snow=t_snow,
            t_ice=t_ice,
            t_dryroad_brk=t_dryroad_brk,
            rr=rr,
            wet=wet,
            wage_prc=wage_prc,
            wage_today_prc=wage_today_prc,
            free_guarantee_yn=free_guarantee_yn,
            t_rlx_isn_yn=t_rlx_isn_yn,
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
