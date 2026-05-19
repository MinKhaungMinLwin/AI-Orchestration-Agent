from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.deal_coupon_item import DealCouponItem


T = TypeVar("T", bound="DealItem")


@_attrs_define
class DealItem:
    """
    Attributes:
        deal_no (str): 기획전 번호
        deal_tp_cd (None | str | Unset): 기획전 유형 코드
        deal_nm (None | str | Unset): 기획전명
        disp_seq (int | None | Unset): 전시 순서
        deal_cpn_tp_cd (None | str | Unset): 기획전 쿠폰 유형 코드
        bnr_pc_img_url (None | str | Unset): 배너 이미지 PC
        bnr_mc_img_url (None | str | Unset): 배너 이미지 모바일
        disp_strt_dtime (None | str | Unset): 전시 시작 일시
        disp_end_dtime (None | str | Unset): 전시 종료 일시
        new_deal_yn (None | str | Unset): 신규 기획전 여부
        deal_brand_logo (None | str | Unset): 기획전 브랜드 로고
        deal_notice (None | str | Unset): 기획전 유의사항
        mapped_coupons (list[DealCouponItem] | Unset): 해당 기획전에 매핑된 활성 쿠폰 목록 (CC_DEAL_CPN_INFO LEFT JOIN). 쿠폰 종류=C301,
            진행상태=40, USE_YN=Y 인 쿠폰만 포함. 비어있으면 쿠폰없이 진행되는 기획전 (즉시할인 등).
    """

    deal_no: str
    deal_tp_cd: None | str | Unset = UNSET
    deal_nm: None | str | Unset = UNSET
    disp_seq: int | None | Unset = UNSET
    deal_cpn_tp_cd: None | str | Unset = UNSET
    bnr_pc_img_url: None | str | Unset = UNSET
    bnr_mc_img_url: None | str | Unset = UNSET
    disp_strt_dtime: None | str | Unset = UNSET
    disp_end_dtime: None | str | Unset = UNSET
    new_deal_yn: None | str | Unset = UNSET
    deal_brand_logo: None | str | Unset = UNSET
    deal_notice: None | str | Unset = UNSET
    mapped_coupons: list[DealCouponItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        deal_no = self.deal_no

        deal_tp_cd: None | str | Unset
        if isinstance(self.deal_tp_cd, Unset):
            deal_tp_cd = UNSET
        else:
            deal_tp_cd = self.deal_tp_cd

        deal_nm: None | str | Unset
        if isinstance(self.deal_nm, Unset):
            deal_nm = UNSET
        else:
            deal_nm = self.deal_nm

        disp_seq: int | None | Unset
        if isinstance(self.disp_seq, Unset):
            disp_seq = UNSET
        else:
            disp_seq = self.disp_seq

        deal_cpn_tp_cd: None | str | Unset
        if isinstance(self.deal_cpn_tp_cd, Unset):
            deal_cpn_tp_cd = UNSET
        else:
            deal_cpn_tp_cd = self.deal_cpn_tp_cd

        bnr_pc_img_url: None | str | Unset
        if isinstance(self.bnr_pc_img_url, Unset):
            bnr_pc_img_url = UNSET
        else:
            bnr_pc_img_url = self.bnr_pc_img_url

        bnr_mc_img_url: None | str | Unset
        if isinstance(self.bnr_mc_img_url, Unset):
            bnr_mc_img_url = UNSET
        else:
            bnr_mc_img_url = self.bnr_mc_img_url

        disp_strt_dtime: None | str | Unset
        if isinstance(self.disp_strt_dtime, Unset):
            disp_strt_dtime = UNSET
        else:
            disp_strt_dtime = self.disp_strt_dtime

        disp_end_dtime: None | str | Unset
        if isinstance(self.disp_end_dtime, Unset):
            disp_end_dtime = UNSET
        else:
            disp_end_dtime = self.disp_end_dtime

        new_deal_yn: None | str | Unset
        if isinstance(self.new_deal_yn, Unset):
            new_deal_yn = UNSET
        else:
            new_deal_yn = self.new_deal_yn

        deal_brand_logo: None | str | Unset
        if isinstance(self.deal_brand_logo, Unset):
            deal_brand_logo = UNSET
        else:
            deal_brand_logo = self.deal_brand_logo

        deal_notice: None | str | Unset
        if isinstance(self.deal_notice, Unset):
            deal_notice = UNSET
        else:
            deal_notice = self.deal_notice

        mapped_coupons: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.mapped_coupons, Unset):
            mapped_coupons = []
            for mapped_coupons_item_data in self.mapped_coupons:
                mapped_coupons_item = mapped_coupons_item_data.to_dict()
                mapped_coupons.append(mapped_coupons_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "deal_no": deal_no,
            }
        )
        if deal_tp_cd is not UNSET:
            field_dict["deal_tp_cd"] = deal_tp_cd
        if deal_nm is not UNSET:
            field_dict["deal_nm"] = deal_nm
        if disp_seq is not UNSET:
            field_dict["disp_seq"] = disp_seq
        if deal_cpn_tp_cd is not UNSET:
            field_dict["deal_cpn_tp_cd"] = deal_cpn_tp_cd
        if bnr_pc_img_url is not UNSET:
            field_dict["bnr_pc_img_url"] = bnr_pc_img_url
        if bnr_mc_img_url is not UNSET:
            field_dict["bnr_mc_img_url"] = bnr_mc_img_url
        if disp_strt_dtime is not UNSET:
            field_dict["disp_strt_dtime"] = disp_strt_dtime
        if disp_end_dtime is not UNSET:
            field_dict["disp_end_dtime"] = disp_end_dtime
        if new_deal_yn is not UNSET:
            field_dict["new_deal_yn"] = new_deal_yn
        if deal_brand_logo is not UNSET:
            field_dict["deal_brand_logo"] = deal_brand_logo
        if deal_notice is not UNSET:
            field_dict["deal_notice"] = deal_notice
        if mapped_coupons is not UNSET:
            field_dict["mapped_coupons"] = mapped_coupons

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.deal_coupon_item import DealCouponItem

        d = dict(src_dict)
        deal_no = d.pop("deal_no")

        def _parse_deal_tp_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        deal_tp_cd = _parse_deal_tp_cd(d.pop("deal_tp_cd", UNSET))

        def _parse_deal_nm(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        deal_nm = _parse_deal_nm(d.pop("deal_nm", UNSET))

        def _parse_disp_seq(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        disp_seq = _parse_disp_seq(d.pop("disp_seq", UNSET))

        def _parse_deal_cpn_tp_cd(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        deal_cpn_tp_cd = _parse_deal_cpn_tp_cd(d.pop("deal_cpn_tp_cd", UNSET))

        def _parse_bnr_pc_img_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        bnr_pc_img_url = _parse_bnr_pc_img_url(d.pop("bnr_pc_img_url", UNSET))

        def _parse_bnr_mc_img_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        bnr_mc_img_url = _parse_bnr_mc_img_url(d.pop("bnr_mc_img_url", UNSET))

        def _parse_disp_strt_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        disp_strt_dtime = _parse_disp_strt_dtime(d.pop("disp_strt_dtime", UNSET))

        def _parse_disp_end_dtime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        disp_end_dtime = _parse_disp_end_dtime(d.pop("disp_end_dtime", UNSET))

        def _parse_new_deal_yn(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        new_deal_yn = _parse_new_deal_yn(d.pop("new_deal_yn", UNSET))

        def _parse_deal_brand_logo(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        deal_brand_logo = _parse_deal_brand_logo(d.pop("deal_brand_logo", UNSET))

        def _parse_deal_notice(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        deal_notice = _parse_deal_notice(d.pop("deal_notice", UNSET))

        _mapped_coupons = d.pop("mapped_coupons", UNSET)
        mapped_coupons: list[DealCouponItem] | Unset = UNSET
        if _mapped_coupons is not UNSET:
            mapped_coupons = []
            for mapped_coupons_item_data in _mapped_coupons:
                mapped_coupons_item = DealCouponItem.from_dict(mapped_coupons_item_data)

                mapped_coupons.append(mapped_coupons_item)

        deal_item = cls(
            deal_no=deal_no,
            deal_tp_cd=deal_tp_cd,
            deal_nm=deal_nm,
            disp_seq=disp_seq,
            deal_cpn_tp_cd=deal_cpn_tp_cd,
            bnr_pc_img_url=bnr_pc_img_url,
            bnr_mc_img_url=bnr_mc_img_url,
            disp_strt_dtime=disp_strt_dtime,
            disp_end_dtime=disp_end_dtime,
            new_deal_yn=new_deal_yn,
            deal_brand_logo=deal_brand_logo,
            deal_notice=deal_notice,
            mapped_coupons=mapped_coupons,
        )

        deal_item.additional_properties = d
        return deal_item

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
