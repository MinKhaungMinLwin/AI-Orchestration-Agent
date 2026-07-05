from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.benefit_applicable_product_item import BenefitApplicableProductItem
    from ..models.benefit_applicable_store_item import BenefitApplicableStoreItem


T = TypeVar("T", bound="BenefitApplicableProductsMatch")


@_attrs_define
class BenefitApplicableProductsMatch:
    """
    Attributes:
        source_type (str): 혜택 유형: coupon / event / deal
        source_id (str): 혜택 식별자: cpn_no / evt_no / deal_no
        total_products (int): 적용 가능한 대표 상품 수
        source_name (None | str | Unset): 혜택명
        products (list[BenefitApplicableProductItem] | Unset): 적용 가능한 대표 상품 목록
        total_stores (int | Unset): 적용 가능한 매장 수 Default: 0.
        stores (list[BenefitApplicableStoreItem] | Unset): 쿠폰에 매장 매핑이 있는 경우 적용 가능 매장 목록
    """

    source_type: str
    source_id: str
    total_products: int
    source_name: None | str | Unset = UNSET
    products: list[BenefitApplicableProductItem] | Unset = UNSET
    total_stores: int | Unset = 0
    stores: list[BenefitApplicableStoreItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        source_type = self.source_type

        source_id = self.source_id

        total_products = self.total_products

        source_name: None | str | Unset
        if isinstance(self.source_name, Unset):
            source_name = UNSET
        else:
            source_name = self.source_name

        products: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.products, Unset):
            products = []
            for products_item_data in self.products:
                products_item = products_item_data.to_dict()
                products.append(products_item)

        total_stores = self.total_stores

        stores: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.stores, Unset):
            stores = []
            for stores_item_data in self.stores:
                stores_item = stores_item_data.to_dict()
                stores.append(stores_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "source_type": source_type,
                "source_id": source_id,
                "total_products": total_products,
            }
        )
        if source_name is not UNSET:
            field_dict["source_name"] = source_name
        if products is not UNSET:
            field_dict["products"] = products
        if total_stores is not UNSET:
            field_dict["total_stores"] = total_stores
        if stores is not UNSET:
            field_dict["stores"] = stores

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.benefit_applicable_product_item import BenefitApplicableProductItem
        from ..models.benefit_applicable_store_item import BenefitApplicableStoreItem

        d = dict(src_dict)
        source_type = d.pop("source_type")

        source_id = d.pop("source_id")

        total_products = d.pop("total_products")

        def _parse_source_name(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        source_name = _parse_source_name(d.pop("source_name", UNSET))

        _products = d.pop("products", UNSET)
        products: list[BenefitApplicableProductItem] | Unset = UNSET
        if _products is not UNSET:
            products = []
            for products_item_data in _products:
                products_item = BenefitApplicableProductItem.from_dict(products_item_data)

                products.append(products_item)

        total_stores = d.pop("total_stores", UNSET)

        _stores = d.pop("stores", UNSET)
        stores: list[BenefitApplicableStoreItem] | Unset = UNSET
        if _stores is not UNSET:
            stores = []
            for stores_item_data in _stores:
                stores_item = BenefitApplicableStoreItem.from_dict(stores_item_data)

                stores.append(stores_item)

        benefit_applicable_products_match = cls(
            source_type=source_type,
            source_id=source_id,
            total_products=total_products,
            source_name=source_name,
            products=products,
            total_stores=total_stores,
            stores=stores,
        )

        benefit_applicable_products_match.additional_properties = d
        return benefit_applicable_products_match

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
