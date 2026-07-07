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
            return [data]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _data_from_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload
    return {}


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


def _normalize_schedule_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    digits = re.sub(r"\D", "", text)
    if len(digits) == 8:
        return f"{digits[:4]}년 {digits[4:6]}월 {digits[6:8]}일"
    return text


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


def _product_card_description(item: dict[str, Any]) -> str:
    explicit = _get_str(
        item,
        "description",
        "goods_desc",
        "pc_prod_tech_desc",
        "pc_prod_remark_desc",
        "slogan",
    )
    if explicit:
        return explicit[:160]

    parts: list[str] = []
    season = _get_str(item, "season_nm")
    car_type = _get_str(item, "car_knd_nm", "car_type")
    performance = _GOODS_PFM_LABELS.get(_get_str(item, "goods_pfm_nm").upper()) or _get_str(item, "goods_dtl_pfm_nm")
    intro = " ".join(part for part in (season, car_type) if part)
    if intro:
        parts.append(f"{intro}용 타이어예요.")
    if performance:
        parts.append(f"{performance} 중심 성향이에요.")
    rating = float(_get_num(item, "rating_avg", "rate", default=0.0))
    review_count = int(_get_num(item, "review_count", "total_qty", default=0))
    if rating and review_count:
        rating_text = int(rating) if rating.is_integer() else f"{rating:g}"
        parts.append(f"평점 {rating_text}점, 리뷰 {review_count}건이에요.")
    elif rating:
        rating_text = int(rating) if rating.is_integer() else f"{rating:g}"
        parts.append(f"평점 {rating_text}점이에요.")
    release = _get_str(item, "t_rls_yearmon")
    if release:
        parts.append(f"{release} 출시 정보가 확인돼요.")
    return " ".join(parts)[:160] or "상품 상세 설명은 /chat 경로에서 추가로 확인할 수 있어요."


def _first_nonempty(values: list[str]) -> str:
    return next((value for value in values if value), "")


def _available_sizes(item: dict[str, Any]) -> list[str]:
    sizes: list[str] = []
    raw_sizes = item.get("available_sizes") or item.get("availableSizes") or item.get("sizes")
    if isinstance(raw_sizes, list):
        sizes.extend(str(size).strip() for size in raw_sizes if str(size).strip())
    for key in ("tire_size", "tireSize", "tire_size_1", "tire_size_2", "tireSize1", "tireSize2"):
        value = _get_str(item, key)
        if value:
            sizes.append(value)
    unique: list[str] = []
    for size in sizes:
        normalized = re.sub(r"\s+", "", size.upper())
        if normalized and normalized not in unique:
            unique.append(normalized)
    return unique


def _comparison_feature(item: dict[str, Any], metric: str) -> str:
    if metric == "release":
        return _first_nonempty([_get_str(item, "t_rls_yearmon"), _get_str(item, "sys_reg_dtime")[:10]])
    if metric == "mileage":
        return _get_str(item, "t_life_span", "t_milg_cvs") or "수명/마일리지 정보 확인되지 않음"
    if metric == "noise":
        grade = _get_str(item, "label_pnwave", "label_pnwave_nm")
        db = _get_str(item, "label_pndb")
        return ", ".join(part for part in (grade, f"{db}dB" if db else "") if part) or "정숙성 정보 확인되지 않음"
    if metric == "fuel_efficiency":
        return _get_str(item, "t_fuel_eff_convert", "rr") or "연비/회전저항 정보 확인되지 않음"
    if metric == "wet":
        return _get_str(item, "wet") or "젖은노면 제동 정보 확인되지 않음"
    if metric == "car_type":
        return _get_str(item, "car_knd_nm", "car_type") or "차종 정보 확인되지 않음"
    values = [
        " / ".join(part for part in (_get_str(item, "goods_pfm_nm"), _get_str(item, "goods_dtl_pfm_nm")) if part),
        _get_str(item, "slogan"),
        _get_str(item, "pc_prod_tech_desc"),
        _get_str(item, "pc_prod_remark_desc"),
    ]
    return _first_nonempty(values)[:120] or "상세 특징 정보는 추가 확인이 필요해요"


def _comparison_metric_note(metric: str) -> str:
    if metric == "fuel_efficiency":
        return "회전저항/RR은 등급 숫자가 낮을수록 연비 효율에 유리한 편입니다."
    if metric == "release":
        return "최신 여부는 DB의 상품 등록일 또는 출시 정보를 기준으로 비교했습니다."
    if metric == "wet":
        return "젖은노면 제동 등급은 규격별로 표시가 다를 수 있어요."
    if metric == "mileage":
        return "마일리지와 수명은 규격, 차종 호환, 주행환경에 따라 체감이 달라질 수 있어요."
    return "표시된 특징은 규격과 차종에 따라 달라질 수 있어요."


def _comparison_rows_for_metric(metric: str) -> tuple[tuple[str, str], ...]:
    if metric == "release":
        return (("출시 시점", "feature"), ("상품 등급", "grade"), ("주요 사이즈", "sizes"))
    if metric == "grade":
        return (("상품 등급", "grade"), ("특징", "feature"), ("평점", "rating"))
    if metric == "mileage":
        return (("마일리지/수명", "feature"), ("상품 등급", "grade"), ("평점", "rating"))
    if metric == "noise":
        return (("정숙성", "feature"), ("상품 등급", "grade"), ("평점", "rating"))
    if metric == "fuel_efficiency":
        return (("연비/회전저항", "feature"), ("상품 등급", "grade"), ("평점", "rating"))
    if metric == "wet":
        return (("빗길 성능", "feature"), ("상품 등급", "grade"), ("평점", "rating"))
    if metric == "car_type":
        return (("차종", "feature"), ("상품 등급", "grade"), ("주요 사이즈", "sizes"))
    return (
        ("특징", "feature"),
        ("상품 등급", "grade"),
        ("주요 성능", "performance"),
        ("평점", "rating"),
        ("주요 사이즈", "sizes"),
    )


def _representative_review_summary(item: dict[str, Any]) -> str:
    reviews = item.get("reviews")
    if not isinstance(reviews, list):
        return ""
    for review in reviews:
        if not isinstance(review, dict):
            continue
        text = _get_str(review, "summary", "review_summary", "gdas_cont", "content")
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            return text[:70].rstrip()
    return ""


def _comparison_value(item: dict[str, Any], metric: str, key: str) -> str:
    if key == "feature":
        return _comparison_feature(item, metric)
    if key == "grade":
        return _get_str(item, "prc_grd_nm") or "미확인"
    if key == "performance":
        return _first_nonempty([
            _get_str(item, "goods_pfm_nm"),
            _get_str(item, "goods_dtl_pfm_nm"),
            _get_str(item, "description"),
        ]) or "확인 가능한 주요 성능 정보가 부족해요"
    if key == "rating":
        rating = _get_num(item, "rating_avg", "rate", default=0.0)
        review_count = int(_get_num(item, "review_count", "total_qty", default=0))
        parts: list[str] = []
        if rating:
            rating_text = int(rating) if float(rating).is_integer() else f"{rating:g}"
            parts.append(f"{rating_text}점")
        if review_count:
            parts.append(f"리뷰 {review_count}건")
        review_summary = _representative_review_summary(item)
        if review_summary:
            parts.append(f"대표 리뷰: {review_summary}")
        return "\n".join(parts) if parts else "평점 정보 확인되지 않음"
    if key == "sizes":
        sizes = _available_sizes(item)
        return ", ".join(sizes[:5]) if sizes else "사이즈 정보 확인되지 않음"
    return "미확인"


def build_product_comparison_template(
    rows_by_requested_name: dict[str, dict[str, Any] | None],
    *,
    compare_metric: str = "detail",
) -> dict[str, Any] | None:
    resolved = [(requested, row) for requested, row in rows_by_requested_name.items() if isinstance(row, dict)]
    if len(resolved) < 2:
        return None
    metric = compare_metric if compare_metric not in ("", "none", None) else "detail"
    lines = ["비교 대상의 특징은 아래처럼 확인돼요.", "", "상품 정보를 상품별 표로 비교해드릴게요."]
    product_names: list[str] = []
    requested_names: list[str] = []
    resolved_products: list[dict[str, Any]] = []
    for requested, row in resolved[:4]:
        display_name = _get_str(row, "goods_nm", "big_goods_nm", "ptrn_d_nm", "title") or requested
        product_names.append(display_name)
        requested_names.append(requested)
        sizes = _available_sizes(row)
        resolved_products.append({
            key: value
            for key, value in {
                "requestedName": requested,
                "goodsNo": _get_str(row, "goods_no", "goodsNo"),
                "productName": display_name,
                "tireSize": sizes[0] if sizes else "",
            }.items()
            if value
        })
        lines.extend(["", f"**{display_name}**", "", "| 항목 | 내용 |", "|---|---|"])
        for label, key in _comparison_rows_for_metric(metric):
            lines.append(f"| {label} | {_comparison_value(row, metric, key)} |")
    lines.extend(["", _comparison_metric_note(metric)])
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": [],
            "predictedDomains": ["DISCOVERY"],
            "metadata": {
                "response_shape_key": "metric_comparison_summary",
                "productNames": product_names[:2],
                "requestedProductNames": requested_names[:2],
                "resolvedProducts": resolved_products[:2],
                "compareMetric": metric,
                "compare_metric": metric,
                "comparison_followup_intent": "none",
                "source": "llm_first_product_comparison",
            },
        },
        "assistant_response_source": "discovery_policy",
    }


def _benefit_rows(payload: Any, section: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    raw_section = data.get(section) if isinstance(data, dict) else None
    return _items_from_payload(raw_section)


def _benefit_line(item: dict[str, Any], *, kind: str) -> str:
    if kind == "event":
        name = _get_str(item, "evt_nm", "event_nm", "title", "name")
        start = _get_str(item, "evt_strt_dtime", "start_date", "startDate")[:10]
        end = _get_str(item, "evt_end_dtime", "end_date", "endDate")[:10]
        link = _get_str(item, "evt_url_addr", "eventUrl", "url")
    else:
        name = _get_str(item, "deal_nm", "deal_nm_ko", "title", "name")
        start = _get_str(item, "deal_strt_dtime", "start_date", "startDate")[:10]
        end = _get_str(item, "deal_end_dtime", "end_date", "endDate")[:10]
        link = _get_str(item, "dtl_conts_url_addr", "dealUrl", "url")
    if not name:
        return ""
    period = f"{start} ~ {end}" if start and end else start or end
    pieces = [name]
    if period:
        pieces.append(period)
    if link:
        pieces.append(link)
    return f"- {' · '.join(pieces)}"


def build_benefit_event_deal_template(payload: Any) -> dict[str, Any]:
    event_rows = _benefit_rows(payload, "events")[:5]
    deal_rows = _benefit_rows(payload, "deals")[:5]
    event_lines = [line for row in event_rows if (line := _benefit_line(row, kind="event"))]
    deal_lines = [line for row in deal_rows if (line := _benefit_line(row, kind="deal"))]
    if not event_lines and not deal_lines:
        assistant_response = "현재 진행 중인 이벤트나 기획전이 없어요. 잠시 후에 다시 확인해 주세요."
    else:
        lines = ["현재 진행 중인 이벤트와 기획전을 안내드릴게요."]
        if event_lines:
            lines.extend(["", "이벤트", *event_lines])
        if deal_lines:
            lines.extend(["", "기획전", *deal_lines])
        lines.extend(["", "자세한 조건은 변경될 수 있어요. 상세 페이지에서 꼭 확인해 주세요."])
        assistant_response = "\n".join(lines)
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": [
                {"label": "진행 중인 이벤트 보기", "url": CTAUrls.PROMOTION_EVENT_LIST, "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
            "metadata": {
                "source": "llm_first_benefit_event_deal_list",
                "response_shape_key": "benefit_event_list_lookup",
                "eventCount": len(event_rows),
                "dealCount": len(deal_rows),
            },
        },
        "assistant_response_source": "code_default_benefit_event_deal",
    }


def build_event_applicable_products_template(payload: Any) -> dict[str, Any]:
    rows = _benefit_rows(payload, "events")
    if not rows:
        assistant_response = "현재 해당 이벤트/기획전/프로모션에 적용 가능한 상품은 확인되지 않아요."
    else:
        lines = ["현재 이벤트/기획전/프로모션 적용 상품이에요."]
        for event in rows[:6]:
            event_name = _get_str(event, "evt_nm", "event_nm", "deal_nm", "title", default="이벤트")
            items = event.get("items")
            if not isinstance(items, list):
                items = []
            product_names: list[str] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = _get_str(item, "goods_nm", "big_goods_nm", "goods_name", "title")
                if name and name not in product_names:
                    product_names.append(name)
            lines.extend(["", f"**{event_name}**"])
            if product_names:
                lines.extend(f"- {name}" for name in product_names[:5])
                if len(product_names) > 5:
                    lines.append(f"- 외 {len(product_names) - 5}개")
            else:
                lines.append("- 적용 상품 확인되지 않음")
        assistant_response = "\n".join(lines)
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": [
                {"label": "진행 중인 이벤트 보기", "url": CTAUrls.PROMOTION_EVENT_LIST, "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
            "metadata": {
                "source": "llm_first_event_applicable_products",
                "response_shape_key": "event_applicable_products_lookup",
            },
        },
        "assistant_response_source": "code_event_applicable_products",
    }


def build_benefit_applicable_products_template(payload: Any) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    query = _get_str(data, "query", default="요청하신 혜택") if isinstance(data, dict) else "요청하신 혜택"
    matches = data.get("matches") if isinstance(data, dict) else None
    if not isinstance(matches, list) or not matches:
        assistant_response = f"'{query}'에 매칭되는 쿠폰/이벤트/기획전 적용 상품은 확인되지 않아요."
    else:
        source_labels = {"coupon": "쿠폰", "event": "이벤트", "deal": "기획전"}
        lines = [f"'{query}'에 매칭되는 적용 상품/매장이에요."]
        for match in matches[:6]:
            if not isinstance(match, dict):
                continue
            source_type = _get_str(match, "source_type")
            source_label = source_labels.get(source_type.lower(), "혜택")
            source_name = _get_str(match, "source_name", default=source_label)
            lines.extend(["", f"**{source_name}** ({source_label})"])
            products = match.get("products")
            product_names: list[str] = []
            if isinstance(products, list):
                for product in products:
                    if not isinstance(product, dict):
                        continue
                    name = _get_str(product, "goods_nm", "goods_name", "big_goods_nm")
                    if name and name not in product_names:
                        product_names.append(name)
            if product_names:
                lines.append("적용 상품:")
                lines.extend(f"- {name}" for name in product_names[:5])
            else:
                lines.append("- 적용 상품 확인되지 않음")
            stores = match.get("stores")
            store_names: list[str] = []
            if isinstance(stores, list):
                for store in stores:
                    if not isinstance(store, dict):
                        continue
                    name = _get_str(store, "shop_nm", "shop_name")
                    if name and name not in store_names:
                        store_names.append(name)
            if store_names:
                lines.append("적용 매장:")
                lines.extend(f"- {name}" for name in store_names[:5])
        assistant_response = "\n".join(lines)
    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": [
                {"label": "진행 중인 이벤트 보기", "url": CTAUrls.PROMOTION_EVENT_LIST, "domain": "DISCOVERY"},
            ],
            "predictedDomains": ["DISCOVERY"],
            "metadata": {
                "source": "llm_first_benefit_applicable_products",
                "response_shape_key": "benefit_applicable_products_lookup",
            },
        },
        "assistant_response_source": "code_benefit_applicable_products",
    }


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
            "description": _product_card_description(item),
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


def _schedule_store_by_shop_id(payload: Any) -> dict[str, dict[str, Any]]:
    data = _data_from_payload(payload)
    schedule = data.get("schedule") if isinstance(data.get("schedule"), dict) else {}
    stores = schedule.get("stores") if isinstance(schedule.get("stores"), list) else []
    by_shop_id: dict[str, dict[str, Any]] = {}
    for store in stores:
        if not isinstance(store, dict):
            continue
        shop_id = _get_str(store, "shop_id", "shopId")
        if shop_id:
            by_shop_id[shop_id] = store
    return by_shop_id


def _location_metadata(payload: Any, item: dict[str, Any], shop_id: str, name: str) -> dict[str, Any]:
    data = _data_from_payload(payload)
    schedule = data.get("schedule") if isinstance(data.get("schedule"), dict) else {}
    schedule_store = _schedule_store_by_shop_id(payload).get(shop_id, {})
    schedule_mode = _get_str(schedule_store, "mode").lower()
    schedule_tier = _get_str(schedule, "tier").lower()
    metadata: dict[str, Any] = {
        "shopId": shop_id,
        "shopName": name,
        "ctaAction": "select_store",
        "cta_action": "select_store",
        "fillsSlot": "shop_id",
        "fills_slot": "shop_id",
    }
    if data.get("schedule") or data.get("inventory") or data.get("logistics") or data.get("candidate_shop_ids"):
        metadata["sourceTool"] = "transaction_store_preview_tool"
        metadata["source_tool"] = "transaction_store_preview_tool"
        metadata["stockCheckMode"] = "preview"
        metadata["stock_check_mode"] = "preview"
    if schedule_mode:
        metadata["scheduleMode"] = schedule_mode
        metadata["schedule_mode"] = schedule_mode
        metadata["inventoryMode"] = schedule_mode
        metadata["inventory_mode"] = schedule_mode
    if schedule_tier:
        metadata["scheduleTier"] = schedule_tier
        metadata["schedule_tier"] = schedule_tier
    for source_key, target_key in (
        ("today_install_yn", "todayInstall"),
        ("todayInstall", "todayInstall"),
        ("tna_delivery_yn", "tnaDelivery"),
        ("tnaDelivery", "tnaDelivery"),
        ("is_installable", "isInstallable"),
        ("installable", "isInstallable"),
    ):
        value = item.get(source_key)
        if value not in (None, "") and target_key not in metadata:
            metadata[target_key] = value
    return metadata


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
        metadata.append(_location_metadata(payload, item, shop_id, name))
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


def _slot_hour(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    try:
        hour = int(digits[:2])
    except ValueError:
        return None
    return hour if 0 <= hour <= 23 and hour != 12 else None


def _datepick_rows_from_slots(payload: Any) -> list[dict[str, Any]]:
    data = _data_from_payload(payload)
    raw_slots = data.get("slots")
    if not isinstance(raw_slots, list):
        return []
    by_day: dict[str, set[int]] = {}
    for slot in raw_slots:
        if not isinstance(slot, dict):
            continue
        day = _normalize_schedule_date(_get_str(slot, "cal_day", "calDay", "date"))
        hour = _slot_hour(slot.get("tm") or slot.get("time") or slot.get("rsv_hour") or slot.get("rsvHour"))
        if day and hour is not None:
            by_day.setdefault(day, set()).add(hour)
    return [
        {
            "date": day,
            "available": bool(hours),
            "availableTimes": sorted(hours),
            "index": idx,
        }
        for idx, (day, hours) in enumerate(sorted(by_day.items()))
    ]


def build_datepick_template(payload: Any, assistant_response: str) -> dict[str, Any] | None:
    slot_rows = _datepick_rows_from_slots(payload)
    if slot_rows:
        data = _data_from_payload(payload)
        metadata = {
            "shopId": _get_str(data, "shop_id", "shopId"),
            "shopName": _get_str(data, "shop_nm", "shopName"),
        }
        return {
            "type": "data",
            "template": "datepick",
            "data": {
                "assistantResponse": assistant_response,
                "dates": slot_rows,
                "metadata": {k: v for k, v in metadata.items() if v},
            },
        }
    rows = _items_from_payload(payload)
    dates = []
    for idx, item in enumerate(rows[:31]):
        date = _normalize_schedule_date(
            item.get("date") or item.get("cal_day") or item.get("calDay") or item.get("requestedCalDay")
        )
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


def build_list_car_template(
    payload: Any,
    assistant_response: str,
    *,
    source_intent: str = "product_compatibility",
) -> dict[str, Any] | None:
    cars = []
    metadata = []
    for item in _items_from_payload(payload)[:5]:
        car_no = _get_str(item, "car_no", "carNo", "licensePlate")
        car_name = _get_str(item, "car_model_det", "car_nm", "carName", "carModelDet")
        maker = _get_str(item, "car_maker", "carMaker")
        info = " ".join(part for part in (maker, car_name) if part).strip() or car_no
        if not car_no or not info:
            continue
        tire_size = _get_str(item, "tire_size_fr", "tireSize")
        tire_size_re = _get_str(item, "tire_size_re", "tireSizeRe")
        cars.append({
            "licensePlate": car_no,
            "info": info,
            "description": info,
            "imageUrl": _get_str(item, "thnl_img_path_nm", "mo_img_path_nm", "pc_img_path_nm"),
        })
        metadata.append({
            "carNo": car_no,
            "car_no": car_no,
            "carLncCd": _get_str(item, "car_lnc_cd", "carLncCd") or None,
            "car_lnc_cd": _get_str(item, "car_lnc_cd", "carLncCd") or None,
            "mbrCarRegSeq": _get_str(item, "mbr_car_reg_seq", "mbr_car_unif_no") or None,
            "mbr_car_reg_seq": _get_str(item, "mbr_car_reg_seq", "mbr_car_unif_no") or None,
            "carMaker": maker or None,
            "carModelDet": _get_str(item, "car_model_det", "carModelDet") or None,
            "car_model_det": _get_str(item, "car_model_det", "carModelDet") or None,
            "carName": _get_str(item, "car_nm", "carName") or None,
            "car_nm": _get_str(item, "car_nm", "carName") or None,
            "carTrim": _get_str(item, "ver_opt_choc", "carTrim") or None,
            "carEngine": _get_str(item, "car_engine", "carEngine") or None,
            "carType": _get_str(item, "car_type", "carType") or None,
            "car_type": _get_str(item, "car_type", "carType") or None,
            "vehicleType": _get_str(item, "vehicle_type", "vehicleType") or None,
            "vehicle_type": _get_str(item, "vehicle_type", "vehicleType") or None,
            "tireSize": tire_size or None,
            "tire_size_fr": tire_size or None,
            "tireSizeRe": tire_size_re or None,
            "tire_size_re": tire_size_re or None,
            "availableSizes": None,
            "available_sizes": None,
            "ctaAction": "select_vehicle_candidate",
            "cta_action": "select_vehicle_candidate",
            "sourceIntent": source_intent,
            "source_intent": source_intent,
            "expectedContractIntent": source_intent,
            "expected_contract_intent": source_intent,
        })
    if not cars:
        return None
    return {
        "type": "data",
        "template": "listCar",
        "data": {
            "assistantResponse": assistant_response,
            "listCar": cars,
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
                    part for part in (_normalize_schedule_date(commerce.schedule.date), commerce.schedule.time) if part
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
