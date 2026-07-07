from __future__ import annotations

import re
from typing import Any

from services.tstation.common.cta_urls import CTAUrls

_PRC_GRD_ALLOWED: frozenset[str] = frozenset({"프리미엄+", "프리미엄", "스탠다드", "이코노미"})
_PRC_GRD_DISPLAY: dict[str, str] = {"프리미엄+": "프리미엄"}
_GOODS_PFM_LABELS: dict[str, str] = {
    "COMFORT": "정숙/승차감",
    "SPORT": "고속/제동성",
    "RUNFLAT": "런플랫",
}
_SVC_CODE_LABELS: dict[str, str] = {
    "113": "픽업&딜리버리",
    "116": "얼라인먼트",
    "119": "타이어 보관",
    "120": "전기차 충전",
    "121": "EV 특화",
    "122": "브레이크",
    "124": "세차",
    "125": "배터리",
    "126": "엔진오일",
}
_MY_COUPON_LINK = {
    "pc": CTAUrls.MY_COUPON_LIST_PC,
    "mobile": CTAUrls.MY_COUPON_LIST_MOBILE,
}


def _items_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data") if isinstance(payload.get("data"), (dict, list)) else payload
        if isinstance(data, dict):
            for key in ("items", "products", "goods", "stores", "coupons", "reservations", "result", "results"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _get_str(item: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def _get_num(item: dict[str, Any], *keys: str, default: int | float = 0) -> int | float:
    for key in keys:
        value = item.get(key)
        if value is None or value == "":
            continue
        try:
            return type(default)(str(value).replace(",", ""))
        except (TypeError, ValueError):
            continue
    return default


def _display_price(item: dict[str, Any]) -> int | None:
    for key in (
        "cheapest_final_prc",
        "final_unit_price",
        "final_prc",
        "final_price",
        "finalPrice",
        "extra_fvr_sale_prc",
        "sale_prc",
        "price",
    ):
        value = int(_get_num(item, key, default=0))
        if value:
            return value
    return None


def _normalize_brand_name(value: str) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def _truthy_flag(value: Any) -> bool:
    return str(value or "").strip().upper() in {"Y", "O", "TRUE", "1"}


def _product_tags(item: dict[str, Any]) -> list[dict[str, Any]]:
    tags: list[dict[str, Any]] = []
    price_grade = _get_str(item, "prc_grd_nm")
    if price_grade in _PRC_GRD_ALLOWED:
        tags.append({"text": _PRC_GRD_DISPLAY.get(price_grade, price_grade), "primary": True})
    performance = _GOODS_PFM_LABELS.get(_get_str(item, "goods_pfm_nm").upper())
    if performance:
        tags.append({"text": performance, "primary": False})
    if _truthy_flag(item.get("sound_absorber_yn")) or "흡음" in _get_str(item, "goods_dtl_pfm_nm"):
        tags.append({"text": "흡음재", "primary": False})
    return tags


def _original_price(item: dict[str, Any], price: int | None) -> int | None:
    original = int(_get_num(item, "sale_prc", "originalPrice", default=0))
    if original:
        return original
    return price


def _discount_amount(item: dict[str, Any], price: int | None, original: int | None) -> int | None:
    explicit = int(_get_num(item, "discount_amt", "discountAmount", default=0))
    if explicit:
        return explicit
    if original and price and original > price:
        return original - price
    return None


def _discount_rate(item: dict[str, Any], discount: int | None, original: int | None) -> float | None:
    explicit = _get_num(item, "extra_fvr_sale_per", "discountRate", default=0.0)
    if explicit:
        return float(explicit)
    if original and discount:
        return round(discount / original * 100, 1)
    return None


def build_product_template(
    payload: Any,
    assistant_response: str,
    *,
    is_booking_flow: bool = False,
) -> dict[str, Any] | None:
    products = []
    metadata = []
    for item in _items_from_payload(payload)[:10]:
        goods_no = str(item.get("goods_no") or item.get("goodsNo") or "").strip()
        name = str(item.get("goods_nm") or item.get("goodsNm") or item.get("title") or item.get("name") or "").strip()
        if not goods_no or not name:
            continue
        price = _display_price(item)
        original_price = _original_price(item, price)
        discount_amount = _discount_amount(item, price, original_price)
        discount_rate = _discount_rate(item, discount_amount, original_price)
        tire_label = _get_str(item, "tire_size_1", "tire_size_2", "tire_size", "size")
        title = f"{name} {tire_label}".strip() if tire_label else name
        products.append({
            "imageUrl": item.get("image_url") or item.get("imageUrl") or "",
            "title": title or goods_no,
            "tires": "",
            "titleProductName": name or goods_no,
            "titleTires": tire_label,
            "brandName": _normalize_brand_name(_get_str(item, "brand_nm", "brandName")),
            "oeBadgeYn": _get_str(item, "oe_badge_yn", "oeBadgeYn"),
            "oeMaker": _get_str(item, "t_oe_maker_1", "oeMaker"),
            "smrtPayYn": _get_str(item, "smrt_pay_yn", "smrtPayYn"),
            "comfort": _get_str(item, "comfort"),
            "price": price,
            "originalPrice": original_price,
            "discountRate": discount_rate,
            "discountAmount": discount_amount,
            "rate": float(_get_num(item, "rate", "rating", "rating_avg", default=0.0)),
            "totalQuantity": int(_get_num(item, "totalQuantity", "total_qty", "review_count", default=0)),
            "tags": _product_tags(item),
            "description": _get_str(item, "description", "goods_desc", "goods_dtl_pfm_nm"),
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
            "isBookingFlow": is_booking_flow,
        },
    }


def _flag(item: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = item.get(key)
        if isinstance(value, bool) and value:
            return True
        if isinstance(value, (int, float)) and value == 1:
            return True
        if _truthy_flag(value):
            return True
    return False


def _join_address(item: dict[str, Any], base_key: str, detail_key: str) -> str:
    return " ".join(part for part in (_get_str(item, base_key), _get_str(item, detail_key)) if part).strip()


def _distance(item: dict[str, Any]) -> str:
    text = _get_str(item, "distance", "distance_text")
    if text:
        return text
    value = item.get("distance_km")
    if isinstance(value, (int, float)):
        return f"{value:.1f}km"
    return ""


def _service_labels(item: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    if _flag(item, "is_all_my_t", "isAllMyT", "all_my_t_yn"):
        labels.append("올마이티")
    if _flag(item, "is_installable", "installable", "install_yn"):
        labels.append("온라인 장착 가능")
    elif any(key in item for key in ("is_installable", "installable", "install_yn")):
        labels.append("온라인 장착 불가")
    if _flag(item, "is_tna_delivery", "tnaDelivery", "tna_delivery_yn"):
        labels.append("T바로배송")
    if _flag(item, "is_ev_specialty", "evSpecialty"):
        labels.append("EV 특화")
    if _flag(item, "is_ev_charge_available", "evChargeAvailable"):
        labels.append("전기차 충전")
    svc_codes = item.get("svc_codes")
    if isinstance(svc_codes, str):
        raw_codes = re.split(r"[,|/\s]+", svc_codes)
    elif isinstance(svc_codes, list):
        raw_codes = [str(code) for code in svc_codes]
    else:
        raw_codes = []
    for code in raw_codes:
        label = _SVC_CODE_LABELS.get(code.strip())
        if label and label not in labels:
            labels.append(label)
    return labels


def _business_hours(item: dict[str, Any]) -> list[str]:
    weekday_start = _get_str(item, "shop_biz_strt_time", "bizStartTime", "weekday_start")
    weekday_end = _get_str(item, "shop_biz_end_time", "bizEndTime", "weekday_end")
    saturday_start = _get_str(item, "shop_sat_strt_time", "satStartTime", "saturday_start")
    saturday_end = _get_str(item, "shop_sat_end_time", "satEndTime", "saturday_end")
    holiday = _get_str(item, "holiday")
    lines: list[str] = []
    if weekday_start or weekday_end:
        lines.append(f"평일: {weekday_start}~{weekday_end}".strip("~"))
    if saturday_start or saturday_end:
        lines.append(f"토요일: {saturday_start}~{saturday_end}".strip("~"))
    if holiday:
        lines.append(f"휴무: {holiday}")
    return lines


def _store_description(item: dict[str, Any], address: str, name: str, shop_id: str) -> str:
    explicit = _get_str(item, "description")
    if explicit and explicit not in {address, name, shop_id}:
        return explicit
    lines: list[str] = []
    if address:
        lines.append(address)
    lines.extend(_business_hours(item))
    tel_no = _get_str(item, "tel_no", "telNo", "phone")
    if tel_no:
        lines.append(f"전화: {tel_no}")
    rating = _get_num(item, "rating_idx", "rating", default=0.0)
    if rating:
        lines.append(f"평점: {float(rating):.1f}")
    review_count = int(_get_num(item, "review_count", "reviewCount", default=-1))
    if review_count >= 0:
        lines.append(f"리뷰 {review_count}건")
    services = _service_labels(item)
    if services:
        lines.append(f"서비스: {' | '.join(services)}")
    stock_label = _get_str(item, "stock_label", "stockLabel")
    if stock_label:
        lines.append(f"[{stock_label}]")
    return "\n ".join(lines) or address or name or shop_id


def build_location_template(payload: Any, assistant_response: str, *, is_booking_flow: bool = False) -> dict[str, Any] | None:
    stores = []
    metadata = []
    for item in _items_from_payload(payload)[:10]:
        shop_id = str(item.get("shop_id") or item.get("shopId") or "").strip()
        name = str(item.get("shop_nm") or item.get("shopName") or item.get("name") or "").strip()
        road_full = _join_address(item, "road_addr_base", "road_addr_dtl")
        jibun_full = _join_address(item, "addr_base", "addr_dtl")
        address = (
            road_full
            or jibun_full
            or _get_str(item, "addr", "address", "road_addr", "roadAddress", "detailAddress")
        )
        if not shop_id and not name:
            continue
        stores.append({
            "nameAddress": name or shop_id,
            "distance": _distance(item),
            "detailAddress": address,
            "isAllMyT": _flag(item, "all_my_t_yn", "isAllMyT", "is_all_my_t"),
            "todayInstall": _flag(item, "today_install_yn", "todayInstall", "today_install"),
            "tnaDelivery": _flag(item, "tna_delivery_yn", "tnaDelivery", "is_tna_delivery"),
            "description": _store_description(item, address, name, shop_id),
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


def build_voucher_template(payload: Any, assistant_response: str) -> dict[str, Any] | None:
    vouchers = []
    metadata = []
    for item in _items_from_payload(payload)[:5]:
        coupon_id = _get_str(item, "cpn_no", "cpn_issu_no", "couponId")
        name = _get_str(item, "cpn_nm", "disp_nm", "nameVoucher", "couponName")
        if not coupon_id or not name:
            continue
        vouchers.append({
            "nameVoucher": name,
            "discount": _get_str(item, "rt_amt_val", "discount"),
            "dateVoucher": _get_str(item, "use_end_dtime", "dateVoucher").split(" ")[0],
            "downloadLink": "",
            "myCouponLink": _MY_COUPON_LINK,
        })
        metadata.append({"couponId": coupon_id})
    if not vouchers:
        return None
    return {
        "type": "data",
        "template": "voucher",
        "data": {
            "assistantResponse": assistant_response,
            "vouchers": vouchers,
            "metadata": metadata,
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
