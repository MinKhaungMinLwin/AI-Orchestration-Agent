from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MemberCarInfo")


@_attrs_define
class MemberCarInfo:
    """
    Attributes:
        car_no (None | str | Unset): 차량 번호
        car_lnc_cd (None | str | Unset): 차량 출시 코드
        car_engine (None | str | Unset): 엔진 형식
        fuel_type (None | str | Unset): 연료 타입
        ver_opt_choc (None | str | Unset): 버전 옵션 선택
        tire_size_fr (None | str | Unset): 전륜 타이어 사이즈
        tire_size_re (None | str | Unset): 후륜 타이어 사이즈
        tot_milg (int | None | Unset): 총 주행거리
        daly_avg_milg (int | None | Unset): 일 평균 주행거리
        car_buy_dt (None | str | Unset): 차량 구매 일자
        car_info_sts_cd (None | str | Unset): 차량 정보 상태 코드
        car_ispt_noti_req_cd (None | str | Unset): 차량 검사 알림 요청 코드
        car_reg_self_auth_yn (None | str | Unset): 차량 등록 본인 인증 여부
        car_info_reg_dt (None | str | Unset): 차량 정보 등록 일자
        car_ownr_nm (None | str | Unset): 차량 소유주 명
        mbr_car_unif_no (None | str | Unset): 회원 차량 통합 번호
        car_auth_yn (None | str | Unset): 차량 인증 여부
        car_nm (None | str | Unset): 차량명
        car_model_det (None | str | Unset): 차량 상세 모델명
        car_eng_vol (None | str | Unset): 차량 배기량
        car_type (None | str | Unset): 차량 타입
        car_origin (None | str | Unset): 차량 제조국
        car_maker (None | str | Unset): 차량 제조사
        pc_img_path_nm (None | str | Unset): PC 이미지 경로
        mo_img_path_nm (None | str | Unset): 모바일 이미지 경로
        thnl_img_path_nm (None | str | Unset): 썸네일 이미지 경로
    """

    car_no: None | str | Unset = UNSET
    car_lnc_cd: None | str | Unset = UNSET
    car_engine: None | str | Unset = UNSET
    fuel_type: None | str | Unset = UNSET
    ver_opt_choc: None | str | Unset = UNSET
    tire_size_fr: None | str | Unset = UNSET
    tire_size_re: None | str | Unset = UNSET
    tot_milg: int | None | Unset = UNSET
    daly_avg_milg: int | None | Unset = UNSET
    car_buy_dt: None | str | Unset = UNSET
    car_info_sts_cd: None | str | Unset = UNSET
    car_ispt_noti_req_cd: None | str | Unset = UNSET
    car_reg_self_auth_yn: None | str | Unset = UNSET
    car_info_reg_dt: None | str | Unset = UNSET
    car_ownr_nm: None | str | Unset = UNSET
    mbr_car_unif_no: None | str | Unset = UNSET
    car_auth_yn: None | str | Unset = UNSET
    car_nm: None | str | Unset = UNSET
    car_model_det: None | str | Unset = UNSET
    car_eng_vol: None | str | Unset = UNSET
    car_type: None | str | Unset = UNSET
    car_origin: None | str | Unset = UNSET
    car_maker: None | str | Unset = UNSET
    pc_img_path_nm: None | str | Unset = UNSET
    mo_img_path_nm: None | str | Unset = UNSET
    thnl_img_path_nm: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        car_no: None | str | Unset
        if isinstance(self.car_no, Unset):
            car_no = UNSET
        else:
            car_no = self.car_no

        car_lnc_cd: None | str | Unset
        if isinstance(self.car_lnc_cd, Unset):
            car_lnc_cd = UNSET
        else:
            car_lnc_cd = self.car_lnc_cd

        car_engine: None | str | Unset
        if isinstance(self.car_engine, Unset):
            car_engine = UNSET
        else:
            car_engine = self.car_engine

        fuel_type: None | str | Unset
        if isinstance(self.fuel_type, Unset):
            fuel_type = UNSET
        else:
            fuel_type = self.fuel_type

        ver_opt_choc: None | str | Unset
        if isinstance(self.ver_opt_choc, Unset):
            ver_opt_choc = UNSET
        else:
            ver_opt_choc = self.ver_opt_choc

        tire_size_fr: None | str | Unset
        if isinstance(self.tire_size_fr, Unset):
            tire_size_fr = UNSET
        else:
            tire_size_fr = self.tire_size_fr

        tire_size_re: None | str | Unset
        if isinstance(self.tire_size_re, Unset):
            tire_size_re = UNSET
        else:
            tire_size_re = self.tire_size_re

        tot_milg: int | None | Unset
        if isinstance(self.tot_milg, Unset):
            tot_milg = UNSET
        else:
            tot_milg = self.tot_milg

        daly_avg_milg: int | None | Unset
        if isinstance(self.daly_avg_milg, Unset):
            daly_avg_milg = UNSET
        else:
            daly_avg_milg = self.daly_avg_milg

        car_buy_dt: None | str | Unset
        if isinstance(self.car_buy_dt, Unset):
            car_buy_dt = UNSET
        else:
            car_buy_dt = self.car_buy_dt

        car_info_sts_cd: None | str | Unset
        if isinstance(self.car_info_sts_cd, Unset):
            car_info_sts_cd = UNSET
        else:
            car_info_sts_cd = self.car_info_sts_cd

        car_ispt_noti_req_cd: None | str | Unset
        if isinstance(self.car_ispt_noti_req_cd, Unset):
            car_ispt_noti_req_cd = UNSET
        else:
            car_ispt_noti_req_cd = self.car_ispt_noti_req_cd

        car_reg_self_auth_yn: None | str | Unset
        if isinstance(self.car_reg_self_auth_yn, Unset):
            car_reg_self_auth_yn = UNSET
        else:
            car_reg_self_auth_yn = self.car_reg_self_auth_yn

        car_info_reg_dt: None | str | Unset
        if isinstance(self.car_info_reg_dt, Unset):
            car_info_reg_dt = UNSET
        else:
            car_info_reg_dt = self.car_info_reg_dt

        car_ownr_nm: None | str | Unset
        if isinstance(self.car_ownr_nm, Unset):
            car_ownr_nm = UNSET
        else:
            car_ownr_nm = self.car_ownr_nm

        mbr_car_unif_no: None | str | Unset
        if isinstance(self.mbr_car_unif_no, Unset):
            mbr_car_unif_no = UNSET
        else:
            mbr_car_unif_no = self.mbr_car_unif_no

        car_auth_yn: None | str | Unset
        if isinstance(self.car_auth_yn, Unset):
            car_auth_yn = UNSET
        else:
            car_auth_yn = self.car_auth_yn

        car_nm: None | str | Unset
        if isinstance(self.car_nm, Unset):
            car_nm = UNSET
        else:
            car_nm = self.car_nm

        car_model_det: None | str | Unset
        if isinstance(self.car_model_det, Unset):
            car_model_det = UNSET
        else:
            car_model_det = self.car_model_det

        car_eng_vol: None | str | Unset
        if isinstance(self.car_eng_vol, Unset):
            car_eng_vol = UNSET
        else:
            car_eng_vol = self.car_eng_vol

        car_type: None | str | Unset
        if isinstance(self.car_type, Unset):
            car_type = UNSET
        else:
            car_type = self.car_type

        car_origin: None | str | Unset
        if isinstance(self.car_origin, Unset):
            car_origin = UNSET
        else:
            car_origin = self.car_origin

        car_maker: None | str | Unset
        if isinstance(self.car_maker, Unset):
            car_maker = UNSET
        else:
            car_maker = self.car_maker

        pc_img_path_nm: None | str | Unset
        if isinstance(self.pc_img_path_nm, Unset):
            pc_img_path_nm = UNSET
        else:
            pc_img_path_nm = self.pc_img_path_nm

        mo_img_path_nm: None | str | Unset
        if isinstance(self.mo_img_path_nm, Unset):
            mo_img_path_nm = UNSET
        else:
            mo_img_path_nm = self.mo_img_path_nm

        thnl_img_path_nm: None | str | Unset
        if isinstance(self.thnl_img_path_nm, Unset):
            thnl_img_path_nm = UNSET
        else:
            thnl_img_path_nm = self.thnl_img_path_nm

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if car_no is not UNSET:
            field_dict["car_no"] = car_no
        if car_lnc_cd is not UNSET:
            field_dict["car_lnc_cd"] = car_lnc_cd
        if car_engine is not UNSET:
            field_dict["car_engine"] = car_engine
        if fuel_type is not UNSET:
            field_dict["fuel_type"] = fuel_type
        if ver_opt_choc is not UNSET:
            field_dict["ver_opt_choc"] = ver_opt_choc
        if tire_size_fr is not UNSET:
            field_dict["tire_size_fr"] = tire_size_fr
        if tire_size_re is not UNSET:
            field_dict["tire_size_re"] = tire_size_re
        if tot_milg is not UNSET:
            field_dict["tot_milg"] = tot_milg
        if daly_avg_milg is not UNSET:
            field_dict["daly_avg_milg"] = daly_avg_milg
        if car_buy_dt is not UNSET:
            field_dict["car_buy_dt"] = car_buy_dt
        if car_info_sts_cd is not UNSET:
            field_dict["car_info_sts_cd"] = car_info_sts_cd
        if car_ispt_noti_req_cd is not UNSET:
            field_dict["car_ispt_noti_req_cd"] = car_ispt_noti_req_cd
        if car_reg_self_auth_yn is not UNSET:
            field_dict["car_reg_self_auth_yn"] = car_reg_self_auth_yn
        if car_info_reg_dt is not UNSET:
            field_dict["car_info_reg_dt"] = car_info_reg_dt
        if car_ownr_nm is not UNSET:
            field_dict["car_ownr_nm"] = car_ownr_nm
        if mbr_car_unif_no is not UNSET:
            field_dict["mbr_car_unif_no"] = mbr_car_unif_no
        if car_auth_yn is not UNSET:
            field_dict["car_auth_yn"] = car_auth_yn
        if car_nm is not UNSET:
            field_dict["car_nm"] = car_nm
        if car_model_det is not UNSET:
            field_dict["car_model_det"] = car_model_det
        if car_eng_vol is not UNSET:
            field_dict["car_eng_vol"] = car_eng_vol
        if car_type is not UNSET:
            field_dict["car_type"] = car_type
        if car_origin is not UNSET:
            field_dict["car_origin"] = car_origin
        if car_maker is not UNSET:
            field_dict["car_maker"] = car_maker
        if pc_img_path_nm is not UNSET:
            field_dict["pc_img_path_nm"] = pc_img_path_nm
        if mo_img_path_nm is not UNSET:
            field_dict["mo_img_path_nm"] = mo_img_path_nm
        if thnl_img_path_nm is not UNSET:
            field_dict["thnl_img_path_nm"] = thnl_img_path_nm

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_car_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_no = _parse_car_no(d.pop("car_no", UNSET))

        def _parse_car_lnc_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_lnc_cd = _parse_car_lnc_cd(d.pop("car_lnc_cd", UNSET))

        def _parse_car_engine(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_engine = _parse_car_engine(d.pop("car_engine", UNSET))

        def _parse_fuel_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        fuel_type = _parse_fuel_type(d.pop("fuel_type", UNSET))

        def _parse_ver_opt_choc(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ver_opt_choc = _parse_ver_opt_choc(d.pop("ver_opt_choc", UNSET))

        def _parse_tire_size_fr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tire_size_fr = _parse_tire_size_fr(d.pop("tire_size_fr", UNSET))

        def _parse_tire_size_re(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        tire_size_re = _parse_tire_size_re(d.pop("tire_size_re", UNSET))

        def _parse_tot_milg(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        tot_milg = _parse_tot_milg(d.pop("tot_milg", UNSET))

        def _parse_daly_avg_milg(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        daly_avg_milg = _parse_daly_avg_milg(d.pop("daly_avg_milg", UNSET))

        def _parse_car_buy_dt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_buy_dt = _parse_car_buy_dt(d.pop("car_buy_dt", UNSET))

        def _parse_car_info_sts_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_info_sts_cd = _parse_car_info_sts_cd(d.pop("car_info_sts_cd", UNSET))

        def _parse_car_ispt_noti_req_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_ispt_noti_req_cd = _parse_car_ispt_noti_req_cd(d.pop("car_ispt_noti_req_cd", UNSET))

        def _parse_car_reg_self_auth_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_reg_self_auth_yn = _parse_car_reg_self_auth_yn(d.pop("car_reg_self_auth_yn", UNSET))

        def _parse_car_info_reg_dt(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_info_reg_dt = _parse_car_info_reg_dt(d.pop("car_info_reg_dt", UNSET))

        def _parse_car_ownr_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_ownr_nm = _parse_car_ownr_nm(d.pop("car_ownr_nm", UNSET))

        def _parse_mbr_car_unif_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mbr_car_unif_no = _parse_mbr_car_unif_no(d.pop("mbr_car_unif_no", UNSET))

        def _parse_car_auth_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_auth_yn = _parse_car_auth_yn(d.pop("car_auth_yn", UNSET))

        def _parse_car_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_nm = _parse_car_nm(d.pop("car_nm", UNSET))

        def _parse_car_model_det(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_model_det = _parse_car_model_det(d.pop("car_model_det", UNSET))

        def _parse_car_eng_vol(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_eng_vol = _parse_car_eng_vol(d.pop("car_eng_vol", UNSET))

        def _parse_car_type(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_type = _parse_car_type(d.pop("car_type", UNSET))

        def _parse_car_origin(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_origin = _parse_car_origin(d.pop("car_origin", UNSET))

        def _parse_car_maker(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_maker = _parse_car_maker(d.pop("car_maker", UNSET))

        def _parse_pc_img_path_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        pc_img_path_nm = _parse_pc_img_path_nm(d.pop("pc_img_path_nm", UNSET))

        def _parse_mo_img_path_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mo_img_path_nm = _parse_mo_img_path_nm(d.pop("mo_img_path_nm", UNSET))

        def _parse_thnl_img_path_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        thnl_img_path_nm = _parse_thnl_img_path_nm(d.pop("thnl_img_path_nm", UNSET))

        member_car_info = cls(
            car_no=car_no,
            car_lnc_cd=car_lnc_cd,
            car_engine=car_engine,
            fuel_type=fuel_type,
            ver_opt_choc=ver_opt_choc,
            tire_size_fr=tire_size_fr,
            tire_size_re=tire_size_re,
            tot_milg=tot_milg,
            daly_avg_milg=daly_avg_milg,
            car_buy_dt=car_buy_dt,
            car_info_sts_cd=car_info_sts_cd,
            car_ispt_noti_req_cd=car_ispt_noti_req_cd,
            car_reg_self_auth_yn=car_reg_self_auth_yn,
            car_info_reg_dt=car_info_reg_dt,
            car_ownr_nm=car_ownr_nm,
            mbr_car_unif_no=mbr_car_unif_no,
            car_auth_yn=car_auth_yn,
            car_nm=car_nm,
            car_model_det=car_model_det,
            car_eng_vol=car_eng_vol,
            car_type=car_type,
            car_origin=car_origin,
            car_maker=car_maker,
            pc_img_path_nm=pc_img_path_nm,
            mo_img_path_nm=mo_img_path_nm,
            thnl_img_path_nm=thnl_img_path_nm,
        )

        member_car_info.additional_properties = d
        return member_car_info

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
