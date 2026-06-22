from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="OrderListItem")


@_attrs_define
class OrderListItem:
    """
    Attributes:
        ord_no (str): 주문 번호
        goods_no (None | str | Unset): 상품 번호 (PR_GOODS_BASE 키)
        goods_nm (None | str | Unset): 상품명
        tire_size_1 (None | str | Unset): 타이어 사이즈 1 (예: 235/45R18)
        tire_size_2 (None | str | Unset): 타이어 사이즈 2 (전/후 다른 사이즈인 경우)
        ord_qty (int | None | Unset): 주문 수량
        sys_reg_dtime (None | str | Unset): 주문 일자 (VW_OP_ORD_BASE.ORD_DTIME, YYYY-MM-DD)
        ispt_car_seq (None | str | Unset): 장착 차량 시퀀스 (VW_OP_ORD_BASE.ISPT_CAR_SEQ)
        car_no (None | str | Unset): 장착 차량 번호
        mbr_car_unif_no (None | str | Unset): 회원 차량 통합 번호
        car_lnc_cd (None | str | Unset): 차량 출시 코드
        car_maker (None | str | Unset): 차량 제조사
        car_model_det (None | str | Unset): 차량 상세 모델명
        car_nm (None | str | Unset): 차량명
        car_tire_size_fr (None | str | Unset): 장착 차량 전륜 타이어 사이즈
        car_tire_size_re (None | str | Unset): 장착 차량 후륜 타이어 사이즈
    """

    ord_no: str
    goods_no: None | str | Unset = UNSET
    goods_nm: None | str | Unset = UNSET
    tire_size_1: None | str | Unset = UNSET
    tire_size_2: None | str | Unset = UNSET
    ord_qty: int | None | Unset = UNSET
    sys_reg_dtime: None | str | Unset = UNSET
    ispt_car_seq: None | str | Unset = UNSET
    car_no: None | str | Unset = UNSET
    mbr_car_unif_no: None | str | Unset = UNSET
    car_lnc_cd: None | str | Unset = UNSET
    car_maker: None | str | Unset = UNSET
    car_model_det: None | str | Unset = UNSET
    car_nm: None | str | Unset = UNSET
    car_tire_size_fr: None | str | Unset = UNSET
    car_tire_size_re: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ord_no = self.ord_no

        goods_no: None | str | Unset
        if isinstance(self.goods_no, Unset):
            goods_no = UNSET
        else:
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

        ord_qty: int | None | Unset
        if isinstance(self.ord_qty, Unset):
            ord_qty = UNSET
        else:
            ord_qty = self.ord_qty

        sys_reg_dtime: None | str | Unset
        if isinstance(self.sys_reg_dtime, Unset):
            sys_reg_dtime = UNSET
        else:
            sys_reg_dtime = self.sys_reg_dtime

        ispt_car_seq: None | str | Unset
        if isinstance(self.ispt_car_seq, Unset):
            ispt_car_seq = UNSET
        else:
            ispt_car_seq = self.ispt_car_seq

        car_no: None | str | Unset
        if isinstance(self.car_no, Unset):
            car_no = UNSET
        else:
            car_no = self.car_no

        mbr_car_unif_no: None | str | Unset
        if isinstance(self.mbr_car_unif_no, Unset):
            mbr_car_unif_no = UNSET
        else:
            mbr_car_unif_no = self.mbr_car_unif_no

        car_lnc_cd: None | str | Unset
        if isinstance(self.car_lnc_cd, Unset):
            car_lnc_cd = UNSET
        else:
            car_lnc_cd = self.car_lnc_cd

        car_maker: None | str | Unset
        if isinstance(self.car_maker, Unset):
            car_maker = UNSET
        else:
            car_maker = self.car_maker

        car_model_det: None | str | Unset
        if isinstance(self.car_model_det, Unset):
            car_model_det = UNSET
        else:
            car_model_det = self.car_model_det

        car_nm: None | str | Unset
        if isinstance(self.car_nm, Unset):
            car_nm = UNSET
        else:
            car_nm = self.car_nm

        car_tire_size_fr: None | str | Unset
        if isinstance(self.car_tire_size_fr, Unset):
            car_tire_size_fr = UNSET
        else:
            car_tire_size_fr = self.car_tire_size_fr

        car_tire_size_re: None | str | Unset
        if isinstance(self.car_tire_size_re, Unset):
            car_tire_size_re = UNSET
        else:
            car_tire_size_re = self.car_tire_size_re

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ord_no": ord_no,
            }
        )
        if goods_no is not UNSET:
            field_dict["goods_no"] = goods_no
        if goods_nm is not UNSET:
            field_dict["goods_nm"] = goods_nm
        if tire_size_1 is not UNSET:
            field_dict["tire_size_1"] = tire_size_1
        if tire_size_2 is not UNSET:
            field_dict["tire_size_2"] = tire_size_2
        if ord_qty is not UNSET:
            field_dict["ord_qty"] = ord_qty
        if sys_reg_dtime is not UNSET:
            field_dict["sys_reg_dtime"] = sys_reg_dtime
        if ispt_car_seq is not UNSET:
            field_dict["ispt_car_seq"] = ispt_car_seq
        if car_no is not UNSET:
            field_dict["car_no"] = car_no
        if mbr_car_unif_no is not UNSET:
            field_dict["mbr_car_unif_no"] = mbr_car_unif_no
        if car_lnc_cd is not UNSET:
            field_dict["car_lnc_cd"] = car_lnc_cd
        if car_maker is not UNSET:
            field_dict["car_maker"] = car_maker
        if car_model_det is not UNSET:
            field_dict["car_model_det"] = car_model_det
        if car_nm is not UNSET:
            field_dict["car_nm"] = car_nm
        if car_tire_size_fr is not UNSET:
            field_dict["car_tire_size_fr"] = car_tire_size_fr
        if car_tire_size_re is not UNSET:
            field_dict["car_tire_size_re"] = car_tire_size_re

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        ord_no = d.pop("ord_no")

        def _parse_goods_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        goods_no = _parse_goods_no(d.pop("goods_no", UNSET))

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

        def _parse_ord_qty(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        ord_qty = _parse_ord_qty(d.pop("ord_qty", UNSET))

        def _parse_sys_reg_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sys_reg_dtime = _parse_sys_reg_dtime(d.pop("sys_reg_dtime", UNSET))

        def _parse_ispt_car_seq(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        ispt_car_seq = _parse_ispt_car_seq(d.pop("ispt_car_seq", UNSET))

        def _parse_car_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_no = _parse_car_no(d.pop("car_no", UNSET))

        def _parse_mbr_car_unif_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mbr_car_unif_no = _parse_mbr_car_unif_no(d.pop("mbr_car_unif_no", UNSET))

        def _parse_car_lnc_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_lnc_cd = _parse_car_lnc_cd(d.pop("car_lnc_cd", UNSET))

        def _parse_car_maker(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_maker = _parse_car_maker(d.pop("car_maker", UNSET))

        def _parse_car_model_det(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_model_det = _parse_car_model_det(d.pop("car_model_det", UNSET))

        def _parse_car_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_nm = _parse_car_nm(d.pop("car_nm", UNSET))

        def _parse_car_tire_size_fr(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_tire_size_fr = _parse_car_tire_size_fr(d.pop("car_tire_size_fr", UNSET))

        def _parse_car_tire_size_re(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_tire_size_re = _parse_car_tire_size_re(d.pop("car_tire_size_re", UNSET))

        order_list_item = cls(
            ord_no=ord_no,
            goods_no=goods_no,
            goods_nm=goods_nm,
            tire_size_1=tire_size_1,
            tire_size_2=tire_size_2,
            ord_qty=ord_qty,
            sys_reg_dtime=sys_reg_dtime,
            ispt_car_seq=ispt_car_seq,
            car_no=car_no,
            mbr_car_unif_no=mbr_car_unif_no,
            car_lnc_cd=car_lnc_cd,
            car_maker=car_maker,
            car_model_det=car_model_det,
            car_nm=car_nm,
            car_tire_size_fr=car_tire_size_fr,
            car_tire_size_re=car_tire_size_re,
        )

        order_list_item.additional_properties = d
        return order_list_item

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
