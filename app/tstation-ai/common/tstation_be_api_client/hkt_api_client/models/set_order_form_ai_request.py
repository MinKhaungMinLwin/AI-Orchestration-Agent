from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="SetOrderFormAIRequest")


@_attrs_define
class SetOrderFormAIRequest:
    """
    Attributes:
        goods_info_arr_str (str): 상품정보 (GOODS_NO|ORD_QTY,...)
        smrt_pay_yn (str): 스마트페이여부 (Y/N)
        drt_pur_yn (str): 주문하기여부 (Y: 주문하기, N: 장바구니)
        shop_seq (None | str | Unset): 방문매장 가맹점주문번호 ET_SHOP_INFO테이블 SHOP_SEQ 컬럼
        shopId (None | str | Unset): 매장 ID (SHOP_ID). shopSeq 누락 시 BE에서 SHOP_SEQ로 변환
        shop_id (None | str | Unset): 매장 ID (SHOP_ID). snake_case 호환 입력
        smrt_pay_inst_mm (None | str | Unset): 스마트페이시 할부개월수 (12/24)
        car_lnc_cd (None | str | Unset): 차량정보 WCODE
        rsv_date (None | str | Unset): 방문 예약일자 (YYYYMMDD)
        rsv_hour (None | str | Unset): 방문 예약시간 (HH, 00~23)
    """

    goods_info_arr_str: str
    smrt_pay_yn: str
    drt_pur_yn: str
    shop_seq: None | str | Unset = UNSET
    shopId: None | str | Unset = UNSET
    shop_id: None | str | Unset = UNSET
    smrt_pay_inst_mm: None | str | Unset = UNSET
    car_lnc_cd: None | str | Unset = UNSET
    rsv_date: None | str | Unset = UNSET
    rsv_hour: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_info_arr_str = self.goods_info_arr_str

        smrt_pay_yn = self.smrt_pay_yn

        drt_pur_yn = self.drt_pur_yn

        shop_seq: None | str | Unset
        if isinstance(self.shop_seq, Unset):
            shop_seq = UNSET
        else:
            shop_seq = self.shop_seq

        shopId: None | str | Unset
        if isinstance(self.shopId, Unset):
            shopId = UNSET
        else:
            shopId = self.shopId

        shop_id: None | str | Unset
        if isinstance(self.shop_id, Unset):
            shop_id = UNSET
        else:
            shop_id = self.shop_id

        smrt_pay_inst_mm: None | str | Unset
        if isinstance(self.smrt_pay_inst_mm, Unset):
            smrt_pay_inst_mm = UNSET
        else:
            smrt_pay_inst_mm = self.smrt_pay_inst_mm

        car_lnc_cd: None | str | Unset
        if isinstance(self.car_lnc_cd, Unset):
            car_lnc_cd = UNSET
        else:
            car_lnc_cd = self.car_lnc_cd

        rsv_date: None | str | Unset
        if isinstance(self.rsv_date, Unset):
            rsv_date = UNSET
        else:
            rsv_date = self.rsv_date

        rsv_hour: None | str | Unset
        if isinstance(self.rsv_hour, Unset):
            rsv_hour = UNSET
        else:
            rsv_hour = self.rsv_hour

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goodsInfoArrStr": goods_info_arr_str,
                "smrtPayYn": smrt_pay_yn,
                "drtPurYn": drt_pur_yn,
            }
        )
        if shop_seq is not UNSET:
            field_dict["shopSeq"] = shop_seq
        if shopId is not UNSET:
            field_dict["shopId"] = shopId
        if shop_id is not UNSET:
            field_dict["shop_id"] = shop_id
        if smrt_pay_inst_mm is not UNSET:
            field_dict["smrtPayInstMm"] = smrt_pay_inst_mm
        if car_lnc_cd is not UNSET:
            field_dict["carLncCd"] = car_lnc_cd
        if rsv_date is not UNSET:
            field_dict["rsvDate"] = rsv_date
        if rsv_hour is not UNSET:
            field_dict["rsvHour"] = rsv_hour

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        goods_info_arr_str = d.pop("goodsInfoArrStr")

        smrt_pay_yn = d.pop("smrtPayYn")

        drt_pur_yn = d.pop("drtPurYn")

        def _parse_shop_seq(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_seq = _parse_shop_seq(d.pop("shopSeq", UNSET))

        def _parse_shopId(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shopId = _parse_shopId(d.pop("shopId", UNSET))

        def _parse_shop_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        shop_id = _parse_shop_id(d.pop("shop_id", UNSET))

        def _parse_smrt_pay_inst_mm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        smrt_pay_inst_mm = _parse_smrt_pay_inst_mm(d.pop("smrtPayInstMm", UNSET))

        def _parse_car_lnc_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        car_lnc_cd = _parse_car_lnc_cd(d.pop("carLncCd", UNSET))

        def _parse_rsv_date(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rsv_date = _parse_rsv_date(d.pop("rsvDate", UNSET))

        def _parse_rsv_hour(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        rsv_hour = _parse_rsv_hour(d.pop("rsvHour", UNSET))

        set_order_form_ai_request = cls(
            goods_info_arr_str=goods_info_arr_str,
            smrt_pay_yn=smrt_pay_yn,
            drt_pur_yn=drt_pur_yn,
            shop_seq=shop_seq,
            shopId=shopId,
            shop_id=shop_id,
            smrt_pay_inst_mm=smrt_pay_inst_mm,
            car_lnc_cd=car_lnc_cd,
            rsv_date=rsv_date,
            rsv_hour=rsv_hour,
        )

        set_order_form_ai_request.additional_properties = d
        return set_order_form_ai_request

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
