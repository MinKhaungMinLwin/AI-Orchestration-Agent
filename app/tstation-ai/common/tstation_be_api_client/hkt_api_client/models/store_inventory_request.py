from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.goods_item import GoodsItem
    from ..models.shop_id_item import ShopIdItem


T = TypeVar("T", bound="StoreInventoryRequest")


@_attrs_define
class StoreInventoryRequest:
    """
    Attributes:
        goods_list (list[GoodsItem]): 재고 확인 상품 목록
        shop_id_list (list[ShopIdItem]): 재고 확인 매장 목록
    """

    goods_list: list[GoodsItem]
    shop_id_list: list[ShopIdItem]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        goods_list = []
        for goods_list_item_data in self.goods_list:
            goods_list_item = goods_list_item_data.to_dict()
            goods_list.append(goods_list_item)

        shop_id_list = []
        for shop_id_list_item_data in self.shop_id_list:
            shop_id_list_item = shop_id_list_item_data.to_dict()
            shop_id_list.append(shop_id_list_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "goodsList": goods_list,
                "shopIdList": shop_id_list,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.goods_item import GoodsItem
        from ..models.shop_id_item import ShopIdItem

        d = dict(src_dict)
        goods_list = []
        _goods_list = d.pop("goodsList")
        for goods_list_item_data in _goods_list:
            goods_list_item = GoodsItem.from_dict(goods_list_item_data)

            goods_list.append(goods_list_item)

        shop_id_list = []
        _shop_id_list = d.pop("shopIdList")
        for shop_id_list_item_data in _shop_id_list:
            shop_id_list_item = ShopIdItem.from_dict(shop_id_list_item_data)

            shop_id_list.append(shop_id_list_item)

        store_inventory_request = cls(
            goods_list=goods_list,
            shop_id_list=shop_id_list,
        )

        store_inventory_request.additional_properties = d
        return store_inventory_request

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
