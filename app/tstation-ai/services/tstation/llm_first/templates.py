from __future__ import annotations

from typing import Any


def _items_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data") if isinstance(payload.get("data"), (dict, list)) else payload
        if isinstance(data, dict):
            for key in ("items", "products", "goods", "stores", "result", "results"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def build_product_template(payload: Any, assistant_response: str) -> dict[str, Any] | None:
    products = []
    metadata = []
    for item in _items_from_payload(payload)[:5]:
        goods_no = str(item.get("goods_no") or item.get("goodsNo") or "").strip()
        name = str(item.get("goods_nm") or item.get("goodsNm") or item.get("title") or item.get("name") or "").strip()
        if not goods_no or not name:
            continue
        price = item.get("extra_fvr_sale_prc") or item.get("sale_prc") or item.get("price")
        tire_label = str(item.get("tire_size_1") or item.get("tire_size") or item.get("size") or "")
        products.append({
            "imageUrl": item.get("image_url") or item.get("imageUrl") or "",
            "title": name or goods_no,
            "tires": tire_label,
            "titleProductName": name or goods_no,
            "titleTires": tire_label,
            "brandName": str(item.get("brand_nm") or item.get("brandName") or ""),
            "price": price,
            "originalPrice": item.get("sale_prc") or item.get("originalPrice"),
            "discountRate": item.get("extra_fvr_sale_per") or item.get("discountRate"),
            "discountAmount": item.get("discount_amt") or item.get("discountAmount"),
            "rate": float(item.get("rating") or item.get("rate") or 0),
            "totalQuantity": int(item.get("review_count") or item.get("totalQuantity") or 0),
            "tags": [],
        })
        metadata.append({"goodsId": goods_no})
    if not products:
        return None
    return {
        "type": "data",
        "template": "product",
        "data": {
            "assistantResponse": assistant_response,
            "products": products,
            "metadata": metadata,
        },
    }


def build_location_template(payload: Any, assistant_response: str, *, is_booking_flow: bool = False) -> dict[str, Any] | None:
    stores = []
    metadata = []
    for item in _items_from_payload(payload)[:10]:
        shop_id = str(item.get("shop_id") or item.get("shopId") or "").strip()
        name = str(item.get("shop_nm") or item.get("shopName") or item.get("name") or "").strip()
        address = str(item.get("addr") or item.get("address") or item.get("road_addr") or item.get("roadAddress") or "").strip()
        if not shop_id and not name:
            continue
        stores.append({
            "nameAddress": name or shop_id,
            "distance": str(item.get("distance") or item.get("distance_text") or ""),
            "detailAddress": address,
            "isAllMyT": bool(item.get("all_my_t_yn") == "Y" or item.get("isAllMyT")),
            "todayInstall": bool(item.get("today_install_yn") == "Y" or item.get("todayInstall")),
            "tnaDelivery": bool(item.get("tna_delivery_yn") == "Y" or item.get("tnaDelivery")),
            "description": str(item.get("description") or address or name or shop_id),
        })
        metadata.append({"shopId": shop_id})
    if not stores:
        return None
    return {
        "type": "data",
        "template": "location",
        "data": {
            "assistantResponse": assistant_response,
            "stores": stores,
            "metadata": metadata,
            "isBookingFlow": is_booking_flow,
        },
    }


def build_datepick_template(payload: Any, assistant_response: str) -> dict[str, Any] | None:
    rows = _items_from_payload(payload)
    dates = []
    for idx, item in enumerate(rows[:31]):
        date = str(item.get("date") or item.get("cal_day") or item.get("calDay") or item.get("requestedCalDay") or "").strip()
        times = item.get("availableTimes") or item.get("times") or item.get("hours") or []
        if isinstance(times, list):
            available_times = [int(t) for t in times if str(t).isdigit() and int(t) != 12]
        else:
            available_times = []
        if date or available_times:
            dates.append({
                "date": date,
                "available": bool(available_times) or bool(item.get("available")),
                "availableTimes": available_times,
                "index": idx,
            })
    if not dates:
        return None
    return {
        "type": "data",
        "template": "datepick",
        "data": {
            "assistantResponse": assistant_response,
            "dates": dates,
            "selectedDate": None,
            "metadata": {},
        },
    }


def build_preorder_template(state: Any, assistant_response: str) -> dict[str, Any] | None:
    commerce = state.commerce_state
    product = commerce.product.product_name or commerce.product.goods_no
    if not (commerce.product.goods_no and product and commerce.quantity):
        return None
    return {
        "type": "data",
        "template": "preOrder",
        "data": {
            "assistantResponse": assistant_response,
            "orderInfo": {
                "carInfo": None,
                "product": product,
                "quantity": commerce.quantity,
                "storeName": commerce.store.shop_name,
                "bookingDateTime": " ".join(
                    part for part in (commerce.schedule.date, commerce.schedule.time) if part
                ) or None,
                "paymentAmount": commerce.price.final_price,
            },
            "isReadyToOrder": bool(
                commerce.product.goods_no
                and commerce.quantity
                and commerce.store.shop_id
                and commerce.schedule.date
                and commerce.schedule.time
                and commerce.price.final_price
            ),
            "isReadyToAddToCart": False,
            "metadata": {
                "goodsId": commerce.product.goods_no,
                "shopId": commerce.store.shop_id,
                "carNo": None,
                "carLncCd": None,
            },
        },
    }
