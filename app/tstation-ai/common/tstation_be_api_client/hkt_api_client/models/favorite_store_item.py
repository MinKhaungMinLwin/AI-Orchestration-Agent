from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="FavoriteStoreItem")


@_attrs_define
class FavoriteStoreItem:
    """회원의 단골매장 1건.

    StoreListItem (매장 목록 카드) 모양에 단골 등록 일시(`favored_at`) 만 추가.
    FE 는 기존 location 카드를 그대로 재사용한다.

        Attributes:
            shop_id (str): 매장 ID (예: 'C01306'). 매장 식별/조회용 비즈니스 키.
            shop_seq (None | str | Unset): 매장 순번 (VW_ET_SHOP_INFO.SHOP_SEQ, 예: 'F203675962'). tstation.com 매장 상세 페이지 URL
                path 값으로 사용 — '/store/locals/{shop_seq}'. shop_id 와는 다른 값이므로 URL 생성 시 반드시 shop_seq 사용.
            shop_nm (None | str | Unset): 매장명
            is_all_my_t (bool | Unset): all my T 매장 여부 (SMART_CARE_SHOP_YN = 'Y') Default: False.
            is_installable (bool | Unset): 쇼핑 장착 가능 매장 여부 (SMART_CARE_SHOP_YN IN ('Y','E')) Default: False.
            is_imported_car (bool | Unset): 수입차 특화점 여부 (ET_SHOP_SPCL_SVC_INFO.SHOP_SPCL_SVC_SCT_CD = '216' 보유 매장) Default:
                False.
            is_ev_specialty (bool | Unset): 전기차 특화점 여부 (ET_SHOP_SPCL_SVC_INFO.SHOP_SPCL_SVC_SCT_CD = '214' 보유 매장) Default:
                False.
            is_ev_charge_available (bool | Unset): 전기차 충전 가능 여부 (ET_SHOP_SPCL_SVC_INFO.SHOP_SPCL_SVC_SCT_CD = '215' 보유 매장)
                Default: False.
            svc_codes (list[str] | None | Unset): 매장이 보유한 서비스 구분 코드 목록 (ET_SHOP_ITEM_SVC_INFO.SHOP_ITEM_SVC_SCT_CD). 노출 코드:
                '113'=타이어(온라인), '116'=배터리(온라인), '119'=타이어 보관서비스(윈터타이어 주문 시 113과 함께 필요), '120'=수입타이어 취급(수입차 특화점은 별도
                is_imported_car 플래그), '121'=경정비-온라인(엔진오일세트/와이퍼/실내필터 등 배터리 외 경정비), '122'=경정비 오늘장착(당일 경정비), '124'=휠얼라이먼트-오프라인,
                '125'=휠얼라이먼트-온라인, '126'=무상점검. 예: 윈터타이어 주문 가능 매장 = ['113','119'] 모두 포함, 배터리+엔진오일 같이 주문 = ['116','121'] 모두 포함,
                휠얼라이먼트 가능 매장 = '124' 또는 '125' 보유
            addr_base (None | str | Unset): 일반주소
            addr_dtl (None | str | Unset): 일반주소
            road_addr_base (None | str | Unset): 도로명주소
            road_addr_dtl (None | str | Unset): 도로명주소 상세
            tel_no (None | str | Unset): 매장 전화번호 (SHOP_TEL_NO)
            shop_biz_strt_time (None | str | Unset): 영업 시작 시간
            shop_biz_end_time (None | str | Unset): 영업 종료 시간
            shop_biz_strt_wday (None | str | Unset): 영업 시작 요일 (예: 월요일)
            shop_biz_end_wday (None | str | Unset): 영업 종료 요일 (예: 금요일)
            shop_sat_strt_time (None | str | Unset): 토요일 영업 시작 시간
            shop_sat_end_time (None | str | Unset): 토요일 영업 종료 시간
            distance_km (float | None | Unset): 좌표 기준 거리 (km), 좌표 검색 시에만 반환
            rating_idx (float | None | Unset): 매장 평점 환산 지수 (ET_SHOP_SCR_INFO.SHOP_EVAL_CVRT_IDX). 평점 없으면 None.
            review_count (int | None | Unset): 정상 리뷰 수 (ET_SHOP_REV_INFO.SHOP_REV_STAT_SCT_CD = '100').
                sort_by='review_count' 정렬 시에만 계산되어 채워짐. 그 외에는 None.
            favored_at (None | str | Unset): 단골매장 등록 일시 (ET_MBR_MYSHOP_INFO.SYS_REG_DTIME, YYYY-MM-DD HH24:MI:SS).
    """

    shop_id: str
    shop_seq: None | str | Unset = UNSET
    shop_nm: None | str | Unset = UNSET
    is_all_my_t: bool | Unset = False
    is_installable: bool | Unset = False
    is_imported_car: bool | Unset = False
    is_ev_specialty: bool | Unset = False
    is_ev_charge_available: bool | Unset = False
    svc_codes: list[str] | None | Unset = UNSET
    addr_base: None | str | Unset = UNSET
    addr_dtl: None | str | Unset = UNSET
    road_addr_base: None | str | Unset = UNSET
    road_addr_dtl: None | str | Unset = UNSET
    tel_no: None | str | Unset = UNSET
    shop_biz_strt_time: None | str | Unset = UNSET
    shop_biz_end_time: None | str | Unset = UNSET
    shop_biz_strt_wday: None | str | Unset = UNSET
    shop_biz_end_wday: None | str | Unset = UNSET
    shop_sat_strt_time: None | str | Unset = UNSET
    shop_sat_end_time: None | str | Unset = UNSET
    distance_km: float | None | Unset = UNSET
    rating_idx: float | None | Unset = UNSET
    review_count: int | None | Unset = UNSET
    favored_at: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        shop_id = self.shop_id

        shop_seq: None | str | Unset
        if isinstance(self.shop_seq, Unset):
            shop_seq = UNSET
        else:
            shop_seq = self.shop_seq

        shop_nm: None | str | Unset
        if isinstance(self.shop_nm, Unset):
            shop_nm = UNSET
        else:
            shop_nm = self.shop_nm

        is_all_my_t = self.is_all_my_t

        is_installable = self.is_installable

        is_imported_car = self.is_imported_car

        is_ev_specialty = self.is_ev_specialty

        is_ev_charge_available = self.is_ev_charge_available

        svc_codes: list[str] | None | Unset
        if isinstance(self.svc_codes, Unset):
            svc_codes = UNSET
        elif isinstance(self.svc_codes, list):
            svc_codes = self.svc_codes

        else:
            svc_codes = self.svc_codes

        addr_base: None | str | Unset
        if isinstance(self.addr_base, Unset):
            addr_base = UNSET
        else:
            addr_base = self.addr_base

        addr_dtl: None | str | Unset
        if isinstance(self.addr_dtl, Unset):
            addr_dtl = UNSET
        else:
            addr_dtl = self.addr_dtl

        road_addr_base: None | str | Unset
        if isinstance(self.road_addr_base, Unset):
            road_addr_base = UNSET
        else:
            road_addr_base = self.road_addr_base

        road_addr_dtl: None | str | Unset
        if isinstance(self.road_addr_dtl, Unset):
            road_addr_dtl = UNSET
        else:
            road_addr_dtl = self.road_addr_dtl

        tel_no: None | str | Unset
        if isinstance(self.tel_no, Unset):
            tel_no = UNSET
        else:
            tel_no = self.tel_no

        shop_biz_strt_time: None | str | Unset
        if isinstance(self.shop_biz_strt_time, Unset):
            shop_biz_strt_time = UNSET
        else:
            shop_biz_strt_time = self.shop_biz_strt_time

        shop_biz_end_time: None | str | Unset
        if isinstance(self.shop_biz_end_time, Unset):
            shop_biz_end_time = UNSET
        else:
            shop_biz_end_time = self.shop_biz_end_time

        shop_biz_strt_wday: None | str | Unset
        if isinstance(self.shop_biz_strt_wday, Unset):
            shop_biz_strt_wday = UNSET
        else:
            shop_biz_strt_wday = self.shop_biz_strt_wday

        shop_biz_end_wday: None | str | Unset
        if isinstance(self.shop_biz_end_wday, Unset):
            shop_biz_end_wday = UNSET
        else:
            shop_biz_end_wday = self.shop_biz_end_wday

        shop_sat_strt_time: None | str | Unset
        if isinstance(self.shop_sat_strt_time, Unset):
            shop_sat_strt_time = UNSET
        else:
            shop_sat_strt_time = self.shop_sat_strt_time

        shop_sat_end_time: None | str | Unset
        if isinstance(self.shop_sat_end_time, Unset):
            shop_sat_end_time = UNSET
        else:
            shop_sat_end_time = self.shop_sat_end_time

        distance_km: float | None | Unset
        if isinstance(self.distance_km, Unset):
            distance_km = UNSET
        else:
            distance_km = self.distance_km

        rating_idx: float | None | Unset
        if isinstance(self.rating_idx, Unset):
            rating_idx = UNSET
        else:
            rating_idx = self.rating_idx

        review_count: int | None | Unset
        if isinstance(self.review_count, Unset):
            review_count = UNSET
        else:
            review_count = self.review_count

        favored_at: None | str | Unset
        if isinstance(self.favored_at, Unset):
            favored_at = UNSET
        else:
            favored_at = self.favored_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "shop_id": shop_id,
            }
        )
        if shop_seq is not UNSET:
            field_dict["shop_seq"] = shop_seq
        if shop_nm is not UNSET:
            field_dict["shop_nm"] = shop_nm
        if is_all_my_t is not UNSET:
            field_dict["is_all_my_t"] = is_all_my_t
        if is_installable is not UNSET:
            field_dict["is_installable"] = is_installable
        if is_imported_car is not UNSET:
            field_dict["is_imported_car"] = is_imported_car
        if is_ev_specialty is not UNSET:
            field_dict["is_ev_specialty"] = is_ev_specialty
        if is_ev_charge_available is not UNSET:
            field_dict["is_ev_charge_available"] = is_ev_charge_available
        if svc_codes is not UNSET:
            field_dict["svc_codes"] = svc_codes
        if addr_base is not UNSET:
            field_dict["addr_base"] = addr_base
        if addr_dtl is not UNSET:
            field_dict["addr_dtl"] = addr_dtl
        if road_addr_base is not UNSET:
            field_dict["road_addr_base"] = road_addr_base
        if road_addr_dtl is not UNSET:
            field_dict["road_addr_dtl"] = road_addr_dtl
        if tel_no is not UNSET:
            field_dict["tel_no"] = tel_no
        if shop_biz_strt_time is not UNSET:
            field_dict["shop_biz_strt_time"] = shop_biz_strt_time
        if shop_biz_end_time is not UNSET:
            field_dict["shop_biz_end_time"] = shop_biz_end_time
        if shop_biz_strt_wday is not UNSET:
            field_dict["shop_biz_strt_wday"] = shop_biz_strt_wday
        if shop_biz_end_wday is not UNSET:
            field_dict["shop_biz_end_wday"] = shop_biz_end_wday
        if shop_sat_strt_time is not UNSET:
            field_dict["shop_sat_strt_time"] = shop_sat_strt_time
        if shop_sat_end_time is not UNSET:
            field_dict["shop_sat_end_time"] = shop_sat_end_time
        if distance_km is not UNSET:
            field_dict["distance_km"] = distance_km
        if rating_idx is not UNSET:
            field_dict["rating_idx"] = rating_idx
        if review_count is not UNSET:
            field_dict["review_count"] = review_count
        if favored_at is not UNSET:
            field_dict["favored_at"] = favored_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        shop_id = d.pop("shop_id")

        def _parse_shop_seq(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_seq = _parse_shop_seq(d.pop("shop_seq", UNSET))

        def _parse_shop_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_nm = _parse_shop_nm(d.pop("shop_nm", UNSET))

        is_all_my_t = d.pop("is_all_my_t", UNSET)

        is_installable = d.pop("is_installable", UNSET)

        is_imported_car = d.pop("is_imported_car", UNSET)

        is_ev_specialty = d.pop("is_ev_specialty", UNSET)

        is_ev_charge_available = d.pop("is_ev_charge_available", UNSET)

        def _parse_svc_codes(data: object) -> list[str] | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, list):
                    raise TypeError()
                svc_codes_type_0 = cast(list[str], data)

                return svc_codes_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(list[str] | None | Unset, data)

        svc_codes = _parse_svc_codes(d.pop("svc_codes", UNSET))

        def _parse_addr_base(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        addr_base = _parse_addr_base(d.pop("addr_base", UNSET))

        def _parse_addr_dtl(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        addr_dtl = _parse_addr_dtl(d.pop("addr_dtl", UNSET))

        def _parse_road_addr_base(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        road_addr_base = _parse_road_addr_base(d.pop("road_addr_base", UNSET))

        def _parse_road_addr_dtl(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        road_addr_dtl = _parse_road_addr_dtl(d.pop("road_addr_dtl", UNSET))

        def _parse_tel_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tel_no = _parse_tel_no(d.pop("tel_no", UNSET))

        def _parse_shop_biz_strt_time(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_biz_strt_time = _parse_shop_biz_strt_time(d.pop("shop_biz_strt_time", UNSET))

        def _parse_shop_biz_end_time(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_biz_end_time = _parse_shop_biz_end_time(d.pop("shop_biz_end_time", UNSET))

        def _parse_shop_biz_strt_wday(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_biz_strt_wday = _parse_shop_biz_strt_wday(d.pop("shop_biz_strt_wday", UNSET))

        def _parse_shop_biz_end_wday(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_biz_end_wday = _parse_shop_biz_end_wday(d.pop("shop_biz_end_wday", UNSET))

        def _parse_shop_sat_strt_time(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_sat_strt_time = _parse_shop_sat_strt_time(d.pop("shop_sat_strt_time", UNSET))

        def _parse_shop_sat_end_time(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_sat_end_time = _parse_shop_sat_end_time(d.pop("shop_sat_end_time", UNSET))

        def _parse_distance_km(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        distance_km = _parse_distance_km(d.pop("distance_km", UNSET))

        def _parse_rating_idx(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        rating_idx = _parse_rating_idx(d.pop("rating_idx", UNSET))

        def _parse_review_count(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        review_count = _parse_review_count(d.pop("review_count", UNSET))

        def _parse_favored_at(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        favored_at = _parse_favored_at(d.pop("favored_at", UNSET))

        favorite_store_item = cls(
            shop_id=shop_id,
            shop_seq=shop_seq,
            shop_nm=shop_nm,
            is_all_my_t=is_all_my_t,
            is_installable=is_installable,
            is_imported_car=is_imported_car,
            is_ev_specialty=is_ev_specialty,
            is_ev_charge_available=is_ev_charge_available,
            svc_codes=svc_codes,
            addr_base=addr_base,
            addr_dtl=addr_dtl,
            road_addr_base=road_addr_base,
            road_addr_dtl=road_addr_dtl,
            tel_no=tel_no,
            shop_biz_strt_time=shop_biz_strt_time,
            shop_biz_end_time=shop_biz_end_time,
            shop_biz_strt_wday=shop_biz_strt_wday,
            shop_biz_end_wday=shop_biz_end_wday,
            shop_sat_strt_time=shop_sat_strt_time,
            shop_sat_end_time=shop_sat_end_time,
            distance_km=distance_km,
            rating_idx=rating_idx,
            review_count=review_count,
            favored_at=favored_at,
        )

        favorite_store_item.additional_properties = d
        return favorite_store_item

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
