"""
Code-based template mapper — replaces LLM UI Template Agent for deterministic tool→template conversion.

Maps domain agent tool outputs directly to FE template format without an LLM call.
Handles 7 "easy" templates; remaining 4 (location, datepick, preOrder, orderComplete)
fall through to the LLM UI Template Agent.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Domain tool → FE template mapping ──────────────────────────────────────────
_TOOL_TEMPLATE_MAP: dict[str, str] = {
    # product
    "search_product_tool": "product",
    "get_products_recommendations_tool": "product",
    # listCar
    "get_my_cars_tool": "listCar",
    "get_user_vehicles_tool": "listCar",
    # voucher
    "get_available_coupons_tool": "voucher",
    "get_my_coupons_tool": "voucher",
    # qnaComplete
    "transfer_to_qna_tool": "qnaComplete",
    # cheapestProduct
    "compare_discount_tool": "cheapestProduct",
    # event — FE에 event 렌더러 없음, LLM fallback
    # "get_events_tool": "event",
    # previewYoutube
    "search_youtube_video_tool": "previewYoutube",
}

_MY_COUPON_LINK = {
    "pc": "https://wwwqa.tstation.com/mypage/tstation/coupon/couponList",
    "mobile": "https://mqa.tstation.com/coupon/myCouponList",
}

_CNSL_TYPE_MAP = {
    "10002": "상품문의",
    "10006": "주문/결제/배송",
    "10010": "반품/교환/환불",
    "10013": "제공서비스/이벤트/혜택",
    "10017": "회원",
    "10019": "기타",
    "10025": "가맹점제휴문의",
    "10034": "이력서접수",
}


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _unwrap(entry: dict) -> dict | list:
    """Unwrap API response: {status: success, data: {actual}} → actual."""
    raw = entry.get("data", {})
    if isinstance(raw, dict) and raw.get("status") == "success":
        return raw.get("data", raw)
    return raw


def _get_str(d: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def _get_num(d: dict, *keys: str, default: int | float = 0) -> int | float:
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return type(default)(v)
            except (ValueError, TypeError):
                pass
    return default


def _find_entries(tool_data_list: list[dict], *tool_names: str) -> list[dict]:
    """Filter accumulated_tool_data by tool name."""
    return [e for e in tool_data_list if e.get("tool", "") in tool_names]


# ── 1. product ──────────────────────────────────────────────────────────────────

def _map_product(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    items, metadata = [], []
    for entry in _find_entries(tool_data_list, "search_product_tool", "get_products_recommendations_tool"):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            goods_nm = _get_str(row, "goods_nm", "title")
            tire_size = _get_str(row, "tire_size_1", "tire_size_2")
            title = f"{goods_nm} {tire_size}".strip() if tire_size else goods_nm
            items.append({
                "imageUrl": _get_str(row, "image_url"),
                "title": title,
                # FE renders these as tag chips (primary/secondary) only when truthy.
                # Tool output has no `tires` field, and `comfort` arrives as a numeric
                # score (e.g. 5.0); stringifying it produced a label that looked like a
                # rating. Skip both — keep the cards clean (FE still shows the rate stars).
                "tires": "",
                "comfort": "",
                "price": int(_get_num(row, "price", "extra_fvr_sale_prc", default=0)),
                "rate": float(_get_num(row, "rate", "rating_avg", default=0.0)),
                "totalQuantity": int(_get_num(row, "totalQuantity", "total_qty", default=0)),
                "description": "",
            })
            metadata.append({"goodsId": _get_str(row, "goods_no")})
    if not items:
        return None
    items, metadata = items[:5], metadata[:5]
    return _build_event("product", {"products": items, "metadata": metadata}, assistant_text, len(items))


# ── 2. listCar ──────────────────────────────────────────────────────────────────

def _map_list_car(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    items, metadata = [], []
    for entry in _find_entries(tool_data_list, "get_my_cars_tool", "get_user_vehicles_tool"):
        raw = _unwrap(entry)
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict):
            # get_my_cars_tool → MemberCarListResponse { items: [] }
            # get_user_vehicles_tool → single dict { car_model, car_model_det, car_nm, ... }
            rows = raw.get("items") if "items" in raw else [raw]
        else:
            rows = []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            car_info = _get_str(row, "car_model_det", "car_nm")
            items.append({
                "licensePlate": _get_str(row, "car_no"),
                "info": car_info,
                "description": car_info,
                "imageUrl": _get_str(row, "thnl_img_path_nm", "mo_img_path_nm", "pc_img_path_nm"),
            })
            metadata.append({
                "carNo": _get_str(row, "car_no"),
                "carLncCd": _get_str(row, "car_lnc_cd"),
            })
    if not items:
        return None
    # 차량 1대면 에이전트가 자동 선택하므로 카드 불필요 → LLM fallback 또는 product 매핑으로
    if len(items) == 1:
        logger.info("[TEMPLATE_MAPPER] Single car — skipping listCar card (auto-selected by agent)")
        return None
    return _build_event("listCar", {"listCar": items, "metadata": metadata}, assistant_text, len(items))


# ── 3. voucher ──────────────────────────────────────────────────────────────────

def _map_voucher(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    vouchers, metadata = [], []
    for entry in _find_entries(tool_data_list, "get_available_coupons_tool", "get_my_coupons_tool"):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else ((raw.get("coupons") or raw.get("items") or []) if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            cpn_no = _get_str(row, "cpn_no", "cpn_issu_no")
            vouchers.append({
                "nameVoucher": _get_str(row, "cpn_nm", "disp_nm"),
                "discount": _get_str(row, "rt_amt_val"),
                "dateVoucher": _get_str(row, "use_end_dtime"),
                "downloadLink": "",
                "myCouponLink": _MY_COUPON_LINK,
            })
            metadata.append({"couponId": cpn_no})
    if not vouchers:
        return None
    return _build_event("voucher", {"vouchers": vouchers, "metadata": metadata}, assistant_text, len(vouchers))


# ── 4. qnaComplete ──────────────────────────────────────────────────────────────

def _map_qna_complete(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    entries = _find_entries(tool_data_list, "transfer_to_qna_tool")
    if not entries:
        return None
    raw = _unwrap(entries[-1])
    if not isinstance(raw, dict):
        return None

    redict_link = raw.get("redictLink") or raw.get("redict_link") or {}
    cnsl_seq = str(raw.get("cnsl_clss_seq") or "")
    cnsl_type = _CNSL_TYPE_MAP.get(cnsl_seq, cnsl_seq)
    title = _get_str(raw, "inq_tit_nm")
    summary = _get_str(raw, "ai_summary")

    if not redict_link:
        return None

    data = {
        "redictLink": redict_link,
        "cnslType": cnsl_type,
        "title": title,
        "summary": summary,
    }
    short = assistant_text.strip() if assistant_text and len(assistant_text.strip()) <= 120 else "1:1 문의가 접수되었습니다. 아래 버튼을 눌러 확인해 주세요."
    return {"type": "data", "template": "qnaComplete", "data": {**data, "assistantResponse": short}}


# ── 5. cheapestProduct ──────────────────────────────────────────────────────────

def _map_cheapest_product(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    entries = _find_entries(tool_data_list, "compare_discount_tool")
    if not entries:
        return None
    raw = _unwrap(entries[-1])
    if not isinstance(raw, dict):
        return None

    rows = raw.get("items", [])
    if not isinstance(rows, list) or not rows:
        return None

    cheapest_no = _get_str(raw, "cheapest_goods_no")
    quantity = int(_get_num(raw, "quantity", default=1))

    items, metadata = [], []
    for row in rows:
        if not isinstance(row, dict):
            continue
        goods_no = _get_str(row, "goods_no")
        # cheapest_goods_no가 있으면 그것만
        if cheapest_no and goods_no != cheapest_no:
            continue
        items.append({
            "title": _get_str(row, "goods_nm", "title", default=goods_no),
            "originalPrice": int(_get_num(row, "sale_prc", default=0)),
            "quantity": quantity,
            "totalDiscount": int(_get_num(row, "total_discount", default=0)),
            "productDiscount": int(_get_num(row, "product_discount", default=0)),
            "couponDiscount": int(_get_num(row, "coupon_discount", default=0)),
            "finalPrice": int(_get_num(row, "final_unit_price", default=0)),
        })
        metadata.append({"goodsId": goods_no})

    if not items:
        return None
    return _build_event("cheapestProduct", {"cheapestProduct": items, "metadata": metadata}, assistant_text, len(items))


# ── 6. event ────────────────────────────────────────────────────────────────────

def _map_event(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    items, metadata = [], []
    for entry in _find_entries(tool_data_list, "get_events_tool"):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            start = _get_str(row, "evt_strt_dtime")
            end = _get_str(row, "evt_end_dtime")
            period = f"{start} ~ {end}" if start and end else start or end or ""
            items.append({
                "eventName": _get_str(row, "evt_nm"),
                "bannerImage": _get_str(row, "bnr_img_url_addr"),
                "eventUrl": _get_str(row, "evt_url_addr"),
                "badge": _get_str(row, "evt_badge_nm"),
                "period": period,
                "actionLink": _get_str(row, "evt_url_addr", "dtl_conts_url_addr"),
                "actionText": "자세히 보기",
            })
            metadata.append({"eventId": _get_str(row, "evt_no")})
    if not items:
        return None
    items, metadata = items[:5], metadata[:5]
    return _build_event("event", {"events": items, "metadata": metadata}, assistant_text, len(items))


# ── 7. previewYoutube ───────────────────────────────────────────────────────────

def _map_preview_youtube(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    items = []
    for entry in _find_entries(tool_data_list, "search_youtube_video_tool"):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else ((raw.get("data") or raw.get("items") or []) if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            items.append({
                "title": _get_str(row, "title"),
                "thumbnailUrl": _get_str(row, "thumbnailUrl", "thumbnail_url"),
                "youtubeUrl": _get_str(row, "url", "youtubeUrl", "youtube_url"),
                "videoId": _get_str(row, "videoId", "video_id"),
            })
    if not items:
        return None
    items = items[:5]
    short = _summarize(assistant_text, "previewYoutube", len(items))
    # previewYoutube: FE reads data.text (not assistantResponse) for intro text
    return {"type": "data", "template": "previewYoutube", "data": {
        "items": items,
        "text": short,
        "assistantResponse": short,
    }}


# ── Common builder ──────────────────────────────────────────────────────────────

def _build_event(template: str, data: dict, assistant_text: str, item_count: int) -> dict:
    """Build a type:data event with a concise assistantResponse."""
    short = _summarize(assistant_text, template, item_count)
    data["assistantResponse"] = short
    return {"type": "data", "template": template, "data": data}


_TEMPLATE_DEFAULTS: dict[str, str] = {
    "product": "고객님, 추천 상품 {n}개를 안내드립니다. 원하시는 상품을 선택해 주세요.",
    "listCar": "고객님, 등록된 차량 {n}대입니다. 차량을 선택해 주세요.",
    "voucher": "고객님, 사용 가능한 쿠폰 {n}개를 안내드립니다.",
    "cheapestProduct": "고객님, 가장 저렴한 상품의 가격을 안내드립니다.",
    "event": "현재 진행 중인 이벤트 {n}개를 안내드립니다.",
    "previewYoutube": "관련 영상 {n}개를 안내드립니다.",
    "qnaComplete": "1:1 문의가 접수되었습니다. 아래 버튼을 눌러 확인해 주세요.",
}


def _summarize(full_text: str, template: str, item_count: int) -> str:
    """Domain Agent 텍스트에서 첫 문장만 추출하거나, 기본 안내를 반환한다.

    PROSE MODE 도입 후 LLM이 1–2문장의 짧은 prose("...찾았어요. ...선택해 주세요 😊")를
    내보내는데, 첫 문장에서 자르면 후반부 + 마지막 emoji가 사라진다. 길이가 120자
    이하라면 그대로 유지하고, 그보다 길 때만 첫 문장 컷을 적용한다.
    """
    text = (full_text or "").strip()
    if not text:
        return _TEMPLATE_DEFAULTS.get(template, "").format(n=item_count)

    if len(text) <= 120:
        return text

    # 길면 첫 문장으로 컷 (줄바꿈 또는 문장 부호 기준)
    for sep in ["\n", ".\n", "!\n", "?\n", ". ", "! ", "? "]:
        idx = text.find(sep)
        if 0 < idx <= 120:
            return text[: idx + 1].strip()

    return _TEMPLATE_DEFAULTS.get(template, "").format(n=item_count)


# ── Mapper registry ─────────────────────────────────────────────────────────────

_MAPPERS: dict[str, Any] = {
    "search_product_tool": _map_product,
    "get_products_recommendations_tool": _map_product,
    "get_my_cars_tool": _map_list_car,
    "get_user_vehicles_tool": _map_list_car,
    "get_available_coupons_tool": _map_voucher,
    "get_my_coupons_tool": _map_voucher,
    "transfer_to_qna_tool": _map_qna_complete,
    "compare_discount_tool": _map_cheapest_product,
    # "get_events_tool": _map_event,  # FE에 event 렌더러 없음
    "search_youtube_video_tool": _map_preview_youtube,
}


def try_build_template(accumulated_tool_data: list[dict], assistant_text: str) -> dict | None:
    """Try to build a template event from accumulated tool data using code mapping.

    Returns a template event dict if a code mapper handled it, or None to fall through
    to the LLM UI Template Agent.
    """
    if not accumulated_tool_data:
        return None

    # When multiple tools are called, pick the most important UI template.
    # Priority: product > listCar > voucher > cheapestProduct > previewYoutube > qnaComplete
    # This handles cases like: get_my_cars → get_products_recommendations → compare_discount
    # where product cards should be shown, not cheapestProduct.
    _PRIORITY = [
        ("search_product_tool", _map_product),
        ("get_products_recommendations_tool", _map_product),
        ("get_my_cars_tool", _map_list_car),
        ("get_user_vehicles_tool", _map_list_car),
        ("get_available_coupons_tool", _map_voucher),
        ("get_my_coupons_tool", _map_voucher),
        ("compare_discount_tool", _map_cheapest_product),
        ("search_youtube_video_tool", _map_preview_youtube),
        ("transfer_to_qna_tool", _map_qna_complete),
    ]

    called_tools = {e.get("tool", "") for e in accumulated_tool_data}

    for tool_name, mapper in _PRIORITY:
        if tool_name in called_tools:
            result = mapper(accumulated_tool_data, assistant_text)
            if result:
                logger.info(
                    "[TEMPLATE_MAPPER] Built '%s' template from %s (skipped UI Template Agent)",
                    result.get("template"),
                    tool_name,
                )
                return result

    return None
