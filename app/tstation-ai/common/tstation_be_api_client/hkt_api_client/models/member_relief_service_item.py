from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="MemberReliefServiceItem")


@_attrs_define
class MemberReliefServiceItem:
    """회원 안심서비스 가입/보상 이력 1건 (VW_ET_MBR_RELIEF_MAST_INFO).

    Attributes:
        relief_join_seq (None | str | Unset): 안심서비스 가입 시퀀스
        ord_no (None | str | Unset): 주문번호
        mbr_no (None | str | Unset): 회원번호
        car_no (None | str | Unset): 차량번호 (뷰에서 마스킹 처리될 수 있음)
        car_model (None | str | Unset): 차량모델
        car_model_det (None | str | Unset): 차량모델상세
        equp_conf_dtime (None | str | Unset): 정비완료시간 (YYYY-MM-DD HH24:MI:SS)
        join_state (None | str | Unset): 안심서비스 가입상태 코드. '100'=정상 / '900'=취소 또는 거절
        join_state_nm (None | str | Unset): 안심서비스 가입상태 한글명
        join_dtime (None | str | Unset): 가입일자시간 (YYYY-MM-DD HH24:MI:SS)
        join_cncl_reason (None | str | Unset): 가입 취소/거절 사유
        relief_state (None | str | Unset): 안심서비스 상태 코드. '100'=가입완료 / '200'=서비스만료(보상처리) / '300'=서비스만료(신규가입) /
            '400'=서비스만료(기간종료) / '900'=정비/결제 취소 / '910'=승인취소(고객요청) / '920'=승인취소(가입불가차량)
        relief_state_nm (None | str | Unset): 안심서비스 상태 한글명
        relief_svc_distance (None | str | Unset): 안심서비스 적용 시 주행거리
        relief_svc_dtime (None | str | Unset): 안심서비스 보상 실행 시간 (YYYY-MM-DD HH24:MI:SS)
        relief_end_dtime (None | str | Unset): 안심서비스 마감 시간 (YYYY-MM-DD HH24:MI:SS)
        relief_end_reason (None | str | Unset): 안심서비스 마감 사유
        plus_yn (None | str | Unset): 안심플러스 여부 Y/N
    """

    relief_join_seq: None | str | Unset = UNSET
    ord_no: None | str | Unset = UNSET
    mbr_no: None | str | Unset = UNSET
    car_no: None | str | Unset = UNSET
    car_model: None | str | Unset = UNSET
    car_model_det: None | str | Unset = UNSET
    equp_conf_dtime: None | str | Unset = UNSET
    join_state: None | str | Unset = UNSET
    join_state_nm: None | str | Unset = UNSET
    join_dtime: None | str | Unset = UNSET
    join_cncl_reason: None | str | Unset = UNSET
    relief_state: None | str | Unset = UNSET
    relief_state_nm: None | str | Unset = UNSET
    relief_svc_distance: None | str | Unset = UNSET
    relief_svc_dtime: None | str | Unset = UNSET
    relief_end_dtime: None | str | Unset = UNSET
    relief_end_reason: None | str | Unset = UNSET
    plus_yn: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        relief_join_seq: None | str | Unset
        if isinstance(self.relief_join_seq, Unset):
            relief_join_seq = UNSET
        else:
            relief_join_seq = self.relief_join_seq

        ord_no: None | str | Unset
        if isinstance(self.ord_no, Unset):
            ord_no = UNSET
        else:
            ord_no = self.ord_no

        mbr_no: None | str | Unset
        if isinstance(self.mbr_no, Unset):
            mbr_no = UNSET
        else:
            mbr_no = self.mbr_no

        car_no: None | str | Unset
        if isinstance(self.car_no, Unset):
            car_no = UNSET
        else:
            car_no = self.car_no

        car_model: None | str | Unset
        if isinstance(self.car_model, Unset):
            car_model = UNSET
        else:
            car_model = self.car_model

        car_model_det: None | str | Unset
        if isinstance(self.car_model_det, Unset):
            car_model_det = UNSET
        else:
            car_model_det = self.car_model_det

        equp_conf_dtime: None | str | Unset
        if isinstance(self.equp_conf_dtime, Unset):
            equp_conf_dtime = UNSET
        else:
            equp_conf_dtime = self.equp_conf_dtime

        join_state: None | str | Unset
        if isinstance(self.join_state, Unset):
            join_state = UNSET
        else:
            join_state = self.join_state

        join_state_nm: None | str | Unset
        if isinstance(self.join_state_nm, Unset):
            join_state_nm = UNSET
        else:
            join_state_nm = self.join_state_nm

        join_dtime: None | str | Unset
        if isinstance(self.join_dtime, Unset):
            join_dtime = UNSET
        else:
            join_dtime = self.join_dtime

        join_cncl_reason: None | str | Unset
        if isinstance(self.join_cncl_reason, Unset):
            join_cncl_reason = UNSET
        else:
            join_cncl_reason = self.join_cncl_reason

        relief_state: None | str | Unset
        if isinstance(self.relief_state, Unset):
            relief_state = UNSET
        else:
            relief_state = self.relief_state

        relief_state_nm: None | str | Unset
        if isinstance(self.relief_state_nm, Unset):
            relief_state_nm = UNSET
        else:
            relief_state_nm = self.relief_state_nm

        relief_svc_distance: None | str | Unset
        if isinstance(self.relief_svc_distance, Unset):
            relief_svc_distance = UNSET
        else:
            relief_svc_distance = self.relief_svc_distance

        relief_svc_dtime: None | str | Unset
        if isinstance(self.relief_svc_dtime, Unset):
            relief_svc_dtime = UNSET
        else:
            relief_svc_dtime = self.relief_svc_dtime

        relief_end_dtime: None | str | Unset
        if isinstance(self.relief_end_dtime, Unset):
            relief_end_dtime = UNSET
        else:
            relief_end_dtime = self.relief_end_dtime

        relief_end_reason: None | str | Unset
        if isinstance(self.relief_end_reason, Unset):
            relief_end_reason = UNSET
        else:
            relief_end_reason = self.relief_end_reason

        plus_yn: None | str | Unset
        if isinstance(self.plus_yn, Unset):
            plus_yn = UNSET
        else:
            plus_yn = self.plus_yn

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if relief_join_seq is not UNSET:
            field_dict["relief_join_seq"] = relief_join_seq
        if ord_no is not UNSET:
            field_dict["ord_no"] = ord_no
        if mbr_no is not UNSET:
            field_dict["mbr_no"] = mbr_no
        if car_no is not UNSET:
            field_dict["car_no"] = car_no
        if car_model is not UNSET:
            field_dict["car_model"] = car_model
        if car_model_det is not UNSET:
            field_dict["car_model_det"] = car_model_det
        if equp_conf_dtime is not UNSET:
            field_dict["equp_conf_dtime"] = equp_conf_dtime
        if join_state is not UNSET:
            field_dict["join_state"] = join_state
        if join_state_nm is not UNSET:
            field_dict["join_state_nm"] = join_state_nm
        if join_dtime is not UNSET:
            field_dict["join_dtime"] = join_dtime
        if join_cncl_reason is not UNSET:
            field_dict["join_cncl_reason"] = join_cncl_reason
        if relief_state is not UNSET:
            field_dict["relief_state"] = relief_state
        if relief_state_nm is not UNSET:
            field_dict["relief_state_nm"] = relief_state_nm
        if relief_svc_distance is not UNSET:
            field_dict["relief_svc_distance"] = relief_svc_distance
        if relief_svc_dtime is not UNSET:
            field_dict["relief_svc_dtime"] = relief_svc_dtime
        if relief_end_dtime is not UNSET:
            field_dict["relief_end_dtime"] = relief_end_dtime
        if relief_end_reason is not UNSET:
            field_dict["relief_end_reason"] = relief_end_reason
        if plus_yn is not UNSET:
            field_dict["plus_yn"] = plus_yn

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_relief_join_seq(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        relief_join_seq = _parse_relief_join_seq(d.pop("relief_join_seq", UNSET))

        def _parse_ord_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ord_no = _parse_ord_no(d.pop("ord_no", UNSET))

        def _parse_mbr_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mbr_no = _parse_mbr_no(d.pop("mbr_no", UNSET))

        def _parse_car_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_no = _parse_car_no(d.pop("car_no", UNSET))

        def _parse_car_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_model = _parse_car_model(d.pop("car_model", UNSET))

        def _parse_car_model_det(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_model_det = _parse_car_model_det(d.pop("car_model_det", UNSET))

        def _parse_equp_conf_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        equp_conf_dtime = _parse_equp_conf_dtime(d.pop("equp_conf_dtime", UNSET))

        def _parse_join_state(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        join_state = _parse_join_state(d.pop("join_state", UNSET))

        def _parse_join_state_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        join_state_nm = _parse_join_state_nm(d.pop("join_state_nm", UNSET))

        def _parse_join_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        join_dtime = _parse_join_dtime(d.pop("join_dtime", UNSET))

        def _parse_join_cncl_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        join_cncl_reason = _parse_join_cncl_reason(d.pop("join_cncl_reason", UNSET))

        def _parse_relief_state(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        relief_state = _parse_relief_state(d.pop("relief_state", UNSET))

        def _parse_relief_state_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        relief_state_nm = _parse_relief_state_nm(d.pop("relief_state_nm", UNSET))

        def _parse_relief_svc_distance(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        relief_svc_distance = _parse_relief_svc_distance(d.pop("relief_svc_distance", UNSET))

        def _parse_relief_svc_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        relief_svc_dtime = _parse_relief_svc_dtime(d.pop("relief_svc_dtime", UNSET))

        def _parse_relief_end_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        relief_end_dtime = _parse_relief_end_dtime(d.pop("relief_end_dtime", UNSET))

        def _parse_relief_end_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        relief_end_reason = _parse_relief_end_reason(d.pop("relief_end_reason", UNSET))

        def _parse_plus_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        plus_yn = _parse_plus_yn(d.pop("plus_yn", UNSET))

        member_relief_service_item = cls(
            relief_join_seq=relief_join_seq,
            ord_no=ord_no,
            mbr_no=mbr_no,
            car_no=car_no,
            car_model=car_model,
            car_model_det=car_model_det,
            equp_conf_dtime=equp_conf_dtime,
            join_state=join_state,
            join_state_nm=join_state_nm,
            join_dtime=join_dtime,
            join_cncl_reason=join_cncl_reason,
            relief_state=relief_state,
            relief_state_nm=relief_state_nm,
            relief_svc_distance=relief_svc_distance,
            relief_svc_dtime=relief_svc_dtime,
            relief_end_dtime=relief_end_dtime,
            relief_end_reason=relief_end_reason,
            plus_yn=plus_yn,
        )

        member_relief_service_item.additional_properties = d
        return member_relief_service_item

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
