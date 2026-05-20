from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.applied_coupon_item import AppliedCouponItem


T = TypeVar("T", bound="RcmdGoodsItem")


@_attrs_define
class RcmdGoodsItem:
    """
    Attributes:
        goods_no (str): 상품 번호
        goods_nm (None | str | Unset): 상품명
        tire_size_1 (None | str | Unset): 타이어 사이즈 (TIRE_SIZE_1, 예: '245/45R18')
        tire_size_2 (None | str | Unset): 타이어 사이즈 후륜 (TIRE_SIZE_2, 전후륜 다른 차량용)
        sale_prc (int | None | Unset): 기본 판매가 (정가, PR_GOODS_DSCNT_PRC_INFO.SALE_PRC 또는
            PR_GOODS_ENTR_DSCNT_PRC_INFO.SALE_PRC). FE 의 originalPrice 매핑 소스.
        extra_fvr_sale_prc (int | None | Unset): 최대 혜택 판매가
        extra_fvr_sale_per (float | None | Unset): 최대 혜택 할인율 (%)
        tot_scr (int | None | Unset): 추천 점수 (TOT_SCR (FST_DISP_YN = ‘Y’ 이면 TOT_SCR * 10), 티스테이션 추천 전용)
        t_comfort (float | None | Unset): 승차감 (T_COMFORT)
        t_silence (float | None | Unset): 정숙성 점수 (T_SILENCE). 내부 추천 점수 — EU 소음 라벨(label_pnwave)과 별개
        t_life_span (float | None | Unset): 수명 (T_LIFE_SPAN)
        t_fuel_eff_convert (float | None | Unset): 연비 (T_FUEL_EFF_CONVERT)
        wet (float | None | Unset): 빗길 성능 (WET)
        t_snow (float | None | Unset): 설상 성능 (T_SNOW)
        t_ice (float | None | Unset): 빙판 성능 (T_ICE)
        t_highspd (float | None | Unset): 고속 주행 성능 (T_HIGHSPD)
        t_highspd_cd (None | str | Unset): 고속 주행 등급 코드 (T_HIGHSPD_CD)
        t_high_hand_avg (float | None | Unset): 핸들링 평균 (T_HIGH_HAND_AVG)
        t_com_sil_avg (float | None | Unset): 정숙성 평균 점수 (T_COM_SIL_AVG). 내부 추천 점수 — EU 소음 라벨과 별개
        t_com_cvs (float | None | Unset): 승차감/정숙성 종합 점수 (T_COM_CVS). 내부 추천 점수 — EU 소음 라벨과 별개
        t_milg_cvs (float | None | Unset): 마일리지 종합 (T_MILG_CVS)
        t_wgt_idx (float | None | Unset): 하중 지수 (T_WGT_IDX)
        t_wgt_idx_kg (float | None | Unset): 하중 지수 KG (T_WGT_IDX_KG)
        t_wgt_spd (None | str | Unset): 하중·속도 (T_WGT_SPD, 예: '95H')
        t_tray_ware (float | None | Unset): 마모 (T_TRAY_WARE)
        t_rlx_isn_yn (None | str | Unset): 안심 보험 여부 (T_RLX_ISN_YN)
        t_high_perform (float | None | Unset): 고속주행성능 (T_HIGH_PERFORM)
        t_handling (float | None | Unset): 핸들링 (T_HANDLING)
        t_dryroad_brk (float | None | Unset): 마른노면 제동력 (T_DRYROAD_BRK)
        rr (None | str | Unset): 회전저항 등급 (RR)
        big_goods_nm (None | str | Unset): 대상품명 (BIG_GOODS_NM)
        ptrn_d_nm (None | str | Unset): 직관적 명칭 (PTRN_D_NM)
        tire_width (None | str | Unset): 단면폭 (TIRE_WIDTH)
        tire_series (None | str | Unset): 편평비 (TIRE_SERIES)
        inch (None | str | Unset): 인치 (INCH)
        brand_nm (None | str | Unset): 브랜드명 (BRAND_NM)
        certify_brand_nm (None | str | Unset): 공식인증 브랜드명 (CERTIFY_BRAND_NM)
        orpl_nm (None | str | Unset): 원산지명 (ORPL_NM)
        t_rls_yearmon (None | str | Unset): 출시년월 (T_RLS_YEARMON)
        wage_prc (int | None | Unset): 공임비 (WAGE_PRC)
        wage_today_prc (int | None | Unset): 오늘공임비 (WAGE_TODAY_PRC)
        free_guarantee_yn (None | str | Unset): 무상교환보증 여부 Y/N (FREE_GUARANTEE_YN)
        goods_pfm_nm (None | str | Unset): 퍼포먼스 분류명 (PR_GOODS_BASE.GOODS_PFM_NM). 값 매핑: 'COMFORT'(정숙/승차감) /
            'SPORT'(고속/제동성) / 'RUNFLAT'(런플랫) 등. 표시·답변용 — 추천 정렬 기준 아님 (orthogonal pfm_nm 필터에서만 사용)
        season_nm (None | str | Unset): 계절 분류명 (SEASON_NM)
        car_knd_nm (None | str | Unset): 차종 분류명 (CAR_KND_NM)
        prc_grd_nm (None | str | Unset): 가격 등급명 (PR_GOODS_BASE.PRC_GRD_NM). 응답값: '프리미엄' (DB 원본 '프리미엄+' 도 응답 단계에서 '프리미엄'
            으로 정규화) / '스탠다드' / '이코노미'. 표시·답변용 — 추천 정렬/필터 기준 아님
        label_pnwave (None | str | Unset): EU 소음 라벨 등급 코드 (LABEL_PNWAVE). 값: 'AA'(최저소음) / 'A'(저소음) / 그 외. 정숙성 내부
            점수(t_silence/t_com_sil_avg)와 별개의 라벨 정보
        label_pnwave_nm (None | str | Unset): EU 소음 라벨 등급명 (DECODE(LABEL_PNWAVE)): '최저소음' / '저소음' / ''. 라벨 표기 — 추천 정렬 기준
            아님
        label_pndb (None | str | Unset): EU 소음 데시벨 라벨 값 (LABEL_PNDB, VARCHAR2). 라벨 표기용 — 정숙성 내부 점수와 별개
        wrt_grte_term (int | None | Unset): 워런티 보증 기간 개월 (WRT_GRTE_TERM)
        rating_avg (float | None | Unset): 평균 평점 (RATING_AVG)
        sys_reg_dtime (None | str | Unset): 상품 등록 일시 (PR_GOODS_BASE.SYS_REG_DTIME, 형식: 'YYYY-MM-DD HH24:MI:SS')
        image_url (None | str | Unset):
        title (None | str | Unset):
        price (int | None | Unset):
        rate (float | None | Unset):
        comfort (float | None | Unset):
        cheapest_final_prc (int | None | Unset): 회원 보유 쿠폰 3-stage 그리디 적용 후 최저가 (회원·상품 매칭 실패 시 null)
        cheapest_total_discount (int | None | Unset): cheapest 시뮬레이션의 총 할인 금액 (sale_prc - cheapest_final_prc)
        cheapest_applied_coupons (list[AppliedCouponItem] | None | Unset): cheapest 시뮬레이션에서 단계별로 적용된 쿠폰 목록
    """

    goods_no: str
    goods_nm: None | str | Unset = UNSET
    tire_size_1: None | str | Unset = UNSET
    tire_size_2: None | str | Unset = UNSET
    sale_prc: int | None | Unset = UNSET
    extra_fvr_sale_prc: int | None | Unset = UNSET
    extra_fvr_sale_per: float | None | Unset = UNSET
    tot_scr: int | None | Unset = UNSET
    t_comfort: float | None | Unset = UNSET
    t_silence: float | None | Unset = UNSET
    t_life_span: float | None | Unset = UNSET
    t_fuel_eff_convert: float | None | Unset = UNSET
    wet: float | None | Unset = UNSET
    t_snow: float | None | Unset = UNSET
    t_ice: float | None | Unset = UNSET
    t_highspd: float | None | Unset = UNSET
    t_highspd_cd: None | str | Unset = UNSET
    t_high_hand_avg: float | None | Unset = UNSET
    t_com_sil_avg: float | None | Unset = UNSET
    t_com_cvs: float | None | Unset = UNSET
    t_milg_cvs: float | None | Unset = UNSET
    t_wgt_idx: float | None | Unset = UNSET
    t_wgt_idx_kg: float | None | Unset = UNSET
    t_wgt_spd: None | str | Unset = UNSET
    t_tray_ware: float | None | Unset = UNSET
    t_rlx_isn_yn: None | str | Unset = UNSET
    t_high_perform: float | None | Unset = UNSET
    t_handling: float | None | Unset = UNSET
    t_dryroad_brk: float | None | Unset = UNSET
    rr: None | str | Unset = UNSET
    big_goods_nm: None | str | Unset = UNSET
    ptrn_d_nm: None | str | Unset = UNSET
    tire_width: None | str | Unset = UNSET
    tire_series: None | str | Unset = UNSET
    inch: None | str | Unset = UNSET
    brand_nm: None | str | Unset = UNSET
    certify_brand_nm: None | str | Unset = UNSET
    orpl_nm: None | str | Unset = UNSET
    t_rls_yearmon: None | str | Unset = UNSET
    wage_prc: int | None | Unset = UNSET
    wage_today_prc: int | None | Unset = UNSET
    free_guarantee_yn: None | str | Unset = UNSET
    goods_pfm_nm: None | str | Unset = UNSET
    season_nm: None | str | Unset = UNSET
    car_knd_nm: None | str | Unset = UNSET
    prc_grd_nm: None | str | Unset = UNSET
    label_pnwave: None | str | Unset = UNSET
    label_pnwave_nm: None | str | Unset = UNSET
    label_pndb: None | str | Unset = UNSET
    wrt_grte_term: int | None | Unset = UNSET
    rating_avg: float | None | Unset = UNSET
    sys_reg_dtime: None | str | Unset = UNSET
    image_url: None | str | Unset = UNSET
    title: None | str | Unset = UNSET
    price: int | None | Unset = UNSET
    rate: float | None | Unset = UNSET
    comfort: float | None | Unset = UNSET
    cheapest_final_prc: int | None | Unset = UNSET
    cheapest_total_discount: int | None | Unset = UNSET
    cheapest_applied_coupons: list[AppliedCouponItem] | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_no = self.goods_no

        goods_nm: None | str | Unset
        if isinstance(self.goods_nm, Unset):
            goods_nm = UNSET
        else:
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

        tot_scr: int | None | Unset
        if isinstance(self.tot_scr, Unset):
            tot_scr = UNSET
        else:
            tot_scr = self.tot_scr

        t_comfort: float | None | Unset
        if isinstance(self.t_comfort, Unset):
            t_comfort = UNSET
        else:
            t_comfort = self.t_comfort

        t_silence: float | None | Unset
        if isinstance(self.t_silence, Unset):
            t_silence = UNSET
        else:
            t_silence = self.t_silence

        t_life_span: float | None | Unset
        if isinstance(self.t_life_span, Unset):
            t_life_span = UNSET
        else:
            t_life_span = self.t_life_span

        t_fuel_eff_convert: float | None | Unset
        if isinstance(self.t_fuel_eff_convert, Unset):
            t_fuel_eff_convert = UNSET
        else:
            t_fuel_eff_convert = self.t_fuel_eff_convert

        wet: float | None | Unset
        if isinstance(self.wet, Unset):
            wet = UNSET
        else:
            wet = self.wet

        t_snow: float | None | Unset
        if isinstance(self.t_snow, Unset):
            t_snow = UNSET
        else:
            t_snow = self.t_snow

        t_ice: float | None | Unset
        if isinstance(self.t_ice, Unset):
            t_ice = UNSET
        else:
            t_ice = self.t_ice

        t_highspd: float | None | Unset
        if isinstance(self.t_highspd, Unset):
            t_highspd = UNSET
        else:
            t_highspd = self.t_highspd

        t_highspd_cd: None | str | Unset
        if isinstance(self.t_highspd_cd, Unset):
            t_highspd_cd = UNSET
        else:
            t_highspd_cd = self.t_highspd_cd

        t_high_hand_avg: float | None | Unset
        if isinstance(self.t_high_hand_avg, Unset):
            t_high_hand_avg = UNSET
        else:
            t_high_hand_avg = self.t_high_hand_avg

        t_com_sil_avg: float | None | Unset
        if isinstance(self.t_com_sil_avg, Unset):
            t_com_sil_avg = UNSET
        else:
            t_com_sil_avg = self.t_com_sil_avg

        t_com_cvs: float | None | Unset
        if isinstance(self.t_com_cvs, Unset):
            t_com_cvs = UNSET
        else:
            t_com_cvs = self.t_com_cvs

        t_milg_cvs: float | None | Unset
        if isinstance(self.t_milg_cvs, Unset):
            t_milg_cvs = UNSET
        else:
            t_milg_cvs = self.t_milg_cvs

        t_wgt_idx: float | None | Unset
        if isinstance(self.t_wgt_idx, Unset):
            t_wgt_idx = UNSET
        else:
            t_wgt_idx = self.t_wgt_idx

        t_wgt_idx_kg: float | None | Unset
        if isinstance(self.t_wgt_idx_kg, Unset):
            t_wgt_idx_kg = UNSET
        else:
            t_wgt_idx_kg = self.t_wgt_idx_kg

        t_wgt_spd: None | str | Unset
        if isinstance(self.t_wgt_spd, Unset):
            t_wgt_spd = UNSET
        else:
            t_wgt_spd = self.t_wgt_spd

        t_tray_ware: float | None | Unset
        if isinstance(self.t_tray_ware, Unset):
            t_tray_ware = UNSET
        else:
            t_tray_ware = self.t_tray_ware

        t_rlx_isn_yn: None | str | Unset
        if isinstance(self.t_rlx_isn_yn, Unset):
            t_rlx_isn_yn = UNSET
        else:
            t_rlx_isn_yn = self.t_rlx_isn_yn

        t_high_perform: float | None | Unset
        if isinstance(self.t_high_perform, Unset):
            t_high_perform = UNSET
        else:
            t_high_perform = self.t_high_perform

        t_handling: float | None | Unset
        if isinstance(self.t_handling, Unset):
            t_handling = UNSET
        else:
            t_handling = self.t_handling

        t_dryroad_brk: float | None | Unset
        if isinstance(self.t_dryroad_brk, Unset):
            t_dryroad_brk = UNSET
        else:
            t_dryroad_brk = self.t_dryroad_brk

        rr: None | str | Unset
        if isinstance(self.rr, Unset):
            rr = UNSET
        else:
            rr = self.rr

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

        goods_pfm_nm: None | str | Unset
        if isinstance(self.goods_pfm_nm, Unset):
            goods_pfm_nm = UNSET
        else:
            goods_pfm_nm = self.goods_pfm_nm

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

        prc_grd_nm: None | str | Unset
        if isinstance(self.prc_grd_nm, Unset):
            prc_grd_nm = UNSET
        else:
            prc_grd_nm = self.prc_grd_nm

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

        wrt_grte_term: int | None | Unset
        if isinstance(self.wrt_grte_term, Unset):
            wrt_grte_term = UNSET
        else:
            wrt_grte_term = self.wrt_grte_term

        rating_avg: float | None | Unset
        if isinstance(self.rating_avg, Unset):
            rating_avg = UNSET
        else:
            rating_avg = self.rating_avg

        sys_reg_dtime: None | str | Unset
        if isinstance(self.sys_reg_dtime, Unset):
            sys_reg_dtime = UNSET
        else:
            sys_reg_dtime = self.sys_reg_dtime

        image_url: None | str | Unset
        if isinstance(self.image_url, Unset):
            image_url = UNSET
        else:
            image_url = self.image_url

        title: None | str | Unset
        if isinstance(self.title, Unset):
            title = UNSET
        else:
            title = self.title

        price: int | None | Unset
        if isinstance(self.price, Unset):
            price = UNSET
        else:
            price = self.price

        rate: float | None | Unset
        if isinstance(self.rate, Unset):
            rate = UNSET
        else:
            rate = self.rate

        comfort: float | None | Unset
        if isinstance(self.comfort, Unset):
            comfort = UNSET
        else:
            comfort = self.comfort

        cheapest_final_prc: int | None | Unset
        if isinstance(self.cheapest_final_prc, Unset):
            cheapest_final_prc = UNSET
        else:
            cheapest_final_prc = self.cheapest_final_prc

        cheapest_total_discount: int | None | Unset
        if isinstance(self.cheapest_total_discount, Unset):
            cheapest_total_discount = UNSET
        else:
            cheapest_total_discount = self.cheapest_total_discount

        cheapest_applied_coupons: list[dict[str, Any]] | None | Unset
        if isinstance(self.cheapest_applied_coupons, Unset):
            cheapest_applied_coupons = UNSET
        elif isinstance(self.cheapest_applied_coupons, list):
            cheapest_applied_coupons = []
            for cheapest_applied_coupons_type_0_item_data in self.cheapest_applied_coupons:
                cheapest_applied_coupons_type_0_item = cheapest_applied_coupons_type_0_item_data.to_dict()
                cheapest_applied_coupons.append(cheapest_applied_coupons_type_0_item)

        else:
            cheapest_applied_coupons = self.cheapest_applied_coupons

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goods_no": goods_no,
            }
        )
        if goods_nm is not UNSET:
            field_dict["goods_nm"] = goods_nm
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
        if tot_scr is not UNSET:
            field_dict["tot_scr"] = tot_scr
        if t_comfort is not UNSET:
            field_dict["t_comfort"] = t_comfort
        if t_silence is not UNSET:
            field_dict["t_silence"] = t_silence
        if t_life_span is not UNSET:
            field_dict["t_life_span"] = t_life_span
        if t_fuel_eff_convert is not UNSET:
            field_dict["t_fuel_eff_convert"] = t_fuel_eff_convert
        if wet is not UNSET:
            field_dict["wet"] = wet
        if t_snow is not UNSET:
            field_dict["t_snow"] = t_snow
        if t_ice is not UNSET:
            field_dict["t_ice"] = t_ice
        if t_highspd is not UNSET:
            field_dict["t_highspd"] = t_highspd
        if t_highspd_cd is not UNSET:
            field_dict["t_highspd_cd"] = t_highspd_cd
        if t_high_hand_avg is not UNSET:
            field_dict["t_high_hand_avg"] = t_high_hand_avg
        if t_com_sil_avg is not UNSET:
            field_dict["t_com_sil_avg"] = t_com_sil_avg
        if t_com_cvs is not UNSET:
            field_dict["t_com_cvs"] = t_com_cvs
        if t_milg_cvs is not UNSET:
            field_dict["t_milg_cvs"] = t_milg_cvs
        if t_wgt_idx is not UNSET:
            field_dict["t_wgt_idx"] = t_wgt_idx
        if t_wgt_idx_kg is not UNSET:
            field_dict["t_wgt_idx_kg"] = t_wgt_idx_kg
        if t_wgt_spd is not UNSET:
            field_dict["t_wgt_spd"] = t_wgt_spd
        if t_tray_ware is not UNSET:
            field_dict["t_tray_ware"] = t_tray_ware
        if t_rlx_isn_yn is not UNSET:
            field_dict["t_rlx_isn_yn"] = t_rlx_isn_yn
        if t_high_perform is not UNSET:
            field_dict["t_high_perform"] = t_high_perform
        if t_handling is not UNSET:
            field_dict["t_handling"] = t_handling
        if t_dryroad_brk is not UNSET:
            field_dict["t_dryroad_brk"] = t_dryroad_brk
        if rr is not UNSET:
            field_dict["rr"] = rr
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
        if brand_nm is not UNSET:
            field_dict["brand_nm"] = brand_nm
        if certify_brand_nm is not UNSET:
            field_dict["certify_brand_nm"] = certify_brand_nm
        if orpl_nm is not UNSET:
            field_dict["orpl_nm"] = orpl_nm
        if t_rls_yearmon is not UNSET:
            field_dict["t_rls_yearmon"] = t_rls_yearmon
        if wage_prc is not UNSET:
            field_dict["wage_prc"] = wage_prc
        if wage_today_prc is not UNSET:
            field_dict["wage_today_prc"] = wage_today_prc
        if free_guarantee_yn is not UNSET:
            field_dict["free_guarantee_yn"] = free_guarantee_yn
        if goods_pfm_nm is not UNSET:
            field_dict["goods_pfm_nm"] = goods_pfm_nm
        if season_nm is not UNSET:
            field_dict["season_nm"] = season_nm
        if car_knd_nm is not UNSET:
            field_dict["car_knd_nm"] = car_knd_nm
        if prc_grd_nm is not UNSET:
            field_dict["prc_grd_nm"] = prc_grd_nm
        if label_pnwave is not UNSET:
            field_dict["label_pnwave"] = label_pnwave
        if label_pnwave_nm is not UNSET:
            field_dict["label_pnwave_nm"] = label_pnwave_nm
        if label_pndb is not UNSET:
            field_dict["label_pndb"] = label_pndb
        if wrt_grte_term is not UNSET:
            field_dict["wrt_grte_term"] = wrt_grte_term
        if rating_avg is not UNSET:
            field_dict["rating_avg"] = rating_avg
        if sys_reg_dtime is not UNSET:
            field_dict["sys_reg_dtime"] = sys_reg_dtime
        if image_url is not UNSET:
            field_dict["image_url"] = image_url
        if title is not UNSET:
            field_dict["title"] = title
        if price is not UNSET:
            field_dict["price"] = price
        if rate is not UNSET:
            field_dict["rate"] = rate
        if comfort is not UNSET:
            field_dict["comfort"] = comfort
        if cheapest_final_prc is not UNSET:
            field_dict["cheapest_final_prc"] = cheapest_final_prc
        if cheapest_total_discount is not UNSET:
            field_dict["cheapest_total_discount"] = cheapest_total_discount
        if cheapest_applied_coupons is not UNSET:
            field_dict["cheapest_applied_coupons"] = cheapest_applied_coupons

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.applied_coupon_item import AppliedCouponItem

        d = dict(src_dict)
        goods_no = d.pop("goods_no")

        def _parse_goods_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        goods_nm = _parse_goods_nm(d.pop("goods_nm", UNSET))

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

        def _parse_tot_scr(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        tot_scr = _parse_tot_scr(d.pop("tot_scr", UNSET))

        def _parse_t_comfort(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_comfort = _parse_t_comfort(d.pop("t_comfort", UNSET))

        def _parse_t_silence(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_silence = _parse_t_silence(d.pop("t_silence", UNSET))

        def _parse_t_life_span(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_life_span = _parse_t_life_span(d.pop("t_life_span", UNSET))

        def _parse_t_fuel_eff_convert(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_fuel_eff_convert = _parse_t_fuel_eff_convert(d.pop("t_fuel_eff_convert", UNSET))

        def _parse_wet(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        wet = _parse_wet(d.pop("wet", UNSET))

        def _parse_t_snow(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_snow = _parse_t_snow(d.pop("t_snow", UNSET))

        def _parse_t_ice(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_ice = _parse_t_ice(d.pop("t_ice", UNSET))

        def _parse_t_highspd(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_highspd = _parse_t_highspd(d.pop("t_highspd", UNSET))

        def _parse_t_highspd_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_highspd_cd = _parse_t_highspd_cd(d.pop("t_highspd_cd", UNSET))

        def _parse_t_high_hand_avg(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_high_hand_avg = _parse_t_high_hand_avg(d.pop("t_high_hand_avg", UNSET))

        def _parse_t_com_sil_avg(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_com_sil_avg = _parse_t_com_sil_avg(d.pop("t_com_sil_avg", UNSET))

        def _parse_t_com_cvs(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_com_cvs = _parse_t_com_cvs(d.pop("t_com_cvs", UNSET))

        def _parse_t_milg_cvs(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_milg_cvs = _parse_t_milg_cvs(d.pop("t_milg_cvs", UNSET))

        def _parse_t_wgt_idx(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_wgt_idx = _parse_t_wgt_idx(d.pop("t_wgt_idx", UNSET))

        def _parse_t_wgt_idx_kg(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_wgt_idx_kg = _parse_t_wgt_idx_kg(d.pop("t_wgt_idx_kg", UNSET))

        def _parse_t_wgt_spd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_wgt_spd = _parse_t_wgt_spd(d.pop("t_wgt_spd", UNSET))

        def _parse_t_tray_ware(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_tray_ware = _parse_t_tray_ware(d.pop("t_tray_ware", UNSET))

        def _parse_t_rlx_isn_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        t_rlx_isn_yn = _parse_t_rlx_isn_yn(d.pop("t_rlx_isn_yn", UNSET))

        def _parse_t_high_perform(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_high_perform = _parse_t_high_perform(d.pop("t_high_perform", UNSET))

        def _parse_t_handling(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_handling = _parse_t_handling(d.pop("t_handling", UNSET))

        def _parse_t_dryroad_brk(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        t_dryroad_brk = _parse_t_dryroad_brk(d.pop("t_dryroad_brk", UNSET))

        def _parse_rr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rr = _parse_rr(d.pop("rr", UNSET))

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

        def _parse_goods_pfm_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        goods_pfm_nm = _parse_goods_pfm_nm(d.pop("goods_pfm_nm", UNSET))

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

        def _parse_prc_grd_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        prc_grd_nm = _parse_prc_grd_nm(d.pop("prc_grd_nm", UNSET))

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

        def _parse_wrt_grte_term(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        wrt_grte_term = _parse_wrt_grte_term(d.pop("wrt_grte_term", UNSET))

        def _parse_rating_avg(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        rating_avg = _parse_rating_avg(d.pop("rating_avg", UNSET))

        def _parse_sys_reg_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sys_reg_dtime = _parse_sys_reg_dtime(d.pop("sys_reg_dtime", UNSET))

        def _parse_image_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        image_url = _parse_image_url(d.pop("image_url", UNSET))

        def _parse_title(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        title = _parse_title(d.pop("title", UNSET))

        def _parse_price(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        price = _parse_price(d.pop("price", UNSET))

        def _parse_rate(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        rate = _parse_rate(d.pop("rate", UNSET))

        def _parse_comfort(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        comfort = _parse_comfort(d.pop("comfort", UNSET))

        def _parse_cheapest_final_prc(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cheapest_final_prc = _parse_cheapest_final_prc(d.pop("cheapest_final_prc", UNSET))

        def _parse_cheapest_total_discount(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        cheapest_total_discount = _parse_cheapest_total_discount(d.pop("cheapest_total_discount", UNSET))

        def _parse_cheapest_applied_coupons(data: object) -> list[AppliedCouponItem] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                cheapest_applied_coupons_type_0 = []
                _cheapest_applied_coupons_type_0 = data
                for cheapest_applied_coupons_type_0_item_data in _cheapest_applied_coupons_type_0:
                    cheapest_applied_coupons_type_0_item = AppliedCouponItem.from_dict(
                        cheapest_applied_coupons_type_0_item_data
                    )

                    cheapest_applied_coupons_type_0.append(cheapest_applied_coupons_type_0_item)

                return cheapest_applied_coupons_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[AppliedCouponItem] | None | Unset, data)

        cheapest_applied_coupons = _parse_cheapest_applied_coupons(d.pop("cheapest_applied_coupons", UNSET))

        rcmd_goods_item = cls(
            goods_no=goods_no,
            goods_nm=goods_nm,
            tire_size_1=tire_size_1,
            tire_size_2=tire_size_2,
            sale_prc=sale_prc,
            extra_fvr_sale_prc=extra_fvr_sale_prc,
            extra_fvr_sale_per=extra_fvr_sale_per,
            tot_scr=tot_scr,
            t_comfort=t_comfort,
            t_silence=t_silence,
            t_life_span=t_life_span,
            t_fuel_eff_convert=t_fuel_eff_convert,
            wet=wet,
            t_snow=t_snow,
            t_ice=t_ice,
            t_highspd=t_highspd,
            t_highspd_cd=t_highspd_cd,
            t_high_hand_avg=t_high_hand_avg,
            t_com_sil_avg=t_com_sil_avg,
            t_com_cvs=t_com_cvs,
            t_milg_cvs=t_milg_cvs,
            t_wgt_idx=t_wgt_idx,
            t_wgt_idx_kg=t_wgt_idx_kg,
            t_wgt_spd=t_wgt_spd,
            t_tray_ware=t_tray_ware,
            t_rlx_isn_yn=t_rlx_isn_yn,
            t_high_perform=t_high_perform,
            t_handling=t_handling,
            t_dryroad_brk=t_dryroad_brk,
            rr=rr,
            big_goods_nm=big_goods_nm,
            ptrn_d_nm=ptrn_d_nm,
            tire_width=tire_width,
            tire_series=tire_series,
            inch=inch,
            brand_nm=brand_nm,
            certify_brand_nm=certify_brand_nm,
            orpl_nm=orpl_nm,
            t_rls_yearmon=t_rls_yearmon,
            wage_prc=wage_prc,
            wage_today_prc=wage_today_prc,
            free_guarantee_yn=free_guarantee_yn,
            goods_pfm_nm=goods_pfm_nm,
            season_nm=season_nm,
            car_knd_nm=car_knd_nm,
            prc_grd_nm=prc_grd_nm,
            label_pnwave=label_pnwave,
            label_pnwave_nm=label_pnwave_nm,
            label_pndb=label_pndb,
            wrt_grte_term=wrt_grte_term,
            rating_avg=rating_avg,
            sys_reg_dtime=sys_reg_dtime,
            image_url=image_url,
            title=title,
            price=price,
            rate=rate,
            comfort=comfort,
            cheapest_final_prc=cheapest_final_prc,
            cheapest_total_discount=cheapest_total_discount,
            cheapest_applied_coupons=cheapest_applied_coupons,
        )

        rcmd_goods_item.additional_properties = d
        return rcmd_goods_item

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
