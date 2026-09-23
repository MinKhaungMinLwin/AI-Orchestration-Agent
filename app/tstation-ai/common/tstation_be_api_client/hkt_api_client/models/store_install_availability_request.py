from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="StoreInstallAvailabilityRequest")


@_attrs_define
class StoreInstallAvailabilityRequest:
    """
    Attributes:
        shop_ids (list[str]): 장착 가능 일정을 확인할 매장 ID 목록
        goods_no (None | str | Unset): 상품 번호. 없으면 재고 판단 없이 단순 방문 예약 범위(general)로 조회
        qty (int | Unset): 장착/구매 수량. goods_no가 있을 때 매장 재고 확인에 사용 Default: 1.
    """

    shop_ids: list[str]
    goods_no: None | str | Unset = UNSET
    qty: int | Unset = 1
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        shop_ids = self.shop_ids

        goods_no: None | str | Unset
        if isinstance(self.goods_no, Unset):
            goods_no = UNSET
        else:
            goods_no = self.goods_no

        qty = self.qty

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "shop_ids": shop_ids,
            }
        )
        if goods_no is not UNSET:
            field_dict["goods_no"] = goods_no
        if qty is not UNSET:
            field_dict["qty"] = qty

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        shop_ids = cast(list[str], d.pop("shop_ids"))

        def _parse_goods_no(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        goods_no = _parse_goods_no(d.pop("goods_no", UNSET))

        qty = d.pop("qty", UNSET)

        store_install_availability_request = cls(
            shop_ids=shop_ids,
            goods_no=goods_no,
            qty=qty,
        )

        store_install_availability_request.additional_properties = d
        return store_install_availability_request

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
