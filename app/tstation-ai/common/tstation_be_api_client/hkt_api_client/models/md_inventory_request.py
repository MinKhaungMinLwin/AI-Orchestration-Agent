from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="MdInventoryRequest")


@_attrs_define
class MdInventoryRequest:
    """
    Attributes:
        goods_no (str): 상품 번호
        shop_id (str): 매장 ID
    """

    goods_no: str
    shop_id: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_no = self.goods_no

        shop_id = self.shop_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goods_no": goods_no,
                "shop_id": shop_id,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        goods_no = d.pop("goods_no")

        shop_id = d.pop("shop_id")

        md_inventory_request = cls(
            goods_no=goods_no,
            shop_id=shop_id,
        )

        md_inventory_request.additional_properties = d
        return md_inventory_request

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
