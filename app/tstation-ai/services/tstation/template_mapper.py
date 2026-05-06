"""
Code-based template mapper — replaces LLM UI Template Agent for deterministic tool→template conversion.

Maps domain agent tool outputs directly to FE template format without an LLM call.
Handles 9 templates (product, listCar, voucher, qnaComplete, cheapestProduct,
previewYoutube, location, datepick, event); remaining 2 (preOrder, orderComplete)
fall through to the LLM UI Template Agent because they require cross-tool context
(car info + price + store + booking time) that the mapper cannot reconstruct from
a single tool output.
"""
import contextvars
import datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Per-request goal_type, set by the chat service before agent.stream() runs.
# Read by _map_location / _map_product to set isBookingFlow when the active
# goal expects a downstream tool call after the user's card pick.
# ContextVar gives request-scoped propagation through the streaming generator
# without threading goal_type through every signature in the agent → mapper
# chain. None means "no active goal / don't override the tool-based default".
current_goal_type: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_goal_type", default=None
)

# Goals whose checklist ends in a downstream tool call after a list-pick.
# Card emits in these goals get isBookingFlow=True so the FE click handler
# routes to /chat (advancing the flow) instead of /append (which only shows
# the description bubble and stops).
# product_recommend is intentionally excluded — it has no checklist; clicking
# a recommended product should still surface the rich description.
_GOAL_BOOKING_FOLLOWUP = frozenset({
    "store_with_stock",
    "place_order",
    "price_inquiry",
})


def _is_goal_booking_followup() -> bool:
    """Read the request-scoped goal_type and decide if isBookingFlow should be
    forced True. Returns False when no goal is set (preserves legacy behavior).
    """
    return current_goal_type.get() in _GOAL_BOOKING_FOLLOWUP

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
    # location
    "get_store_list_tool": "location",
    "get_nearby_stores_tool": "location",
    # datepick
    "get_store_schedule_tool": "datepick",
}

# Booking-flow signals: tools that imply the customer is mid-purchase, not just
# browsing for store info. Used by `_map_location` to set `isBookingFlow`.
# Notably excludes `get_store_detail_tool` — Flow 5 General now calls it as a
# description-enrichment companion to `get_store_list_tool` (info-only intent),
# so its presence is not a booking signal. Date-specific schedule/detail flows
# either trip the schedule mapper first (datepick) or are guarded out earlier.
_BOOKING_SIGNAL_TOOLS = frozenset({
    "get_store_inventory_tool",
    "get_logistics_inventory_tool",
    "get_store_schedule_tool",
    "get_multi_store_schedule_tool",
    "get_final_price_tool",
    "save_to_cart_tool",
    "quick_order_tool",
})

# Korean short weekday labels used for datepick `date` strings.
_WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")

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


def _yyyymmdd_to_korean_date(s: str) -> str:
    """'20260422' → '2026년 4월 22일 (수)'. Returns the input unchanged on parse failure."""
    try:
        dt = datetime.datetime.strptime(s, "%Y%m%d")
    except (ValueError, TypeError):
        return s
    return f"{dt.year}년 {dt.month}월 {dt.day}일 ({_WEEKDAY_KO[dt.weekday()]})"


def _normalize_time(s: str) -> str:
    """Normalize a BE business-hours value to ``HH:MM``.

    The store endpoints return inconsistent shapes — sometimes ``"09:00"``,
    sometimes just ``"09"`` — which produces awkward mixed output like
    ``평일 09~19 / 토요일 09:00~16:00``. Pad single-hour, ``"H"`` (e.g. ``"9"``)
    and ``"HHMM"`` (e.g. ``"0930"``) shapes; pass through anything else
    unchanged so we never silently mangle a value we don't recognise.
    """
    s = (s or "").strip()
    if not s:
        return s
    if ":" in s:
        h, _, m = s.partition(":")
        try:
            return f"{int(h):02d}:{int(m):02d}"
        except ValueError:
            return s
    if s.isdigit():
        try:
            if len(s) <= 2:
                return f"{int(s):02d}:00"
            if len(s) == 4:
                return f"{int(s[:2]):02d}:{int(s[2:]):02d}"
        except ValueError:
            return s
    return s


# ── 1. product ──────────────────────────────────────────────────────────────────

def _map_product(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    # TEMP DEBUG: dump entry shape so we can see what keys actually arrive at runtime.
    logger.info(
        "[_map_product DEBUG] tools=%s, get_final_price_entries=%s",
        [e.get("tool") for e in tool_data_list],
        [
            {"keys": list(e.keys()), "args": e.get("args"), "input": e.get("input"), "data_keys": list((e.get("data") or {}).keys()) if isinstance(e.get("data"), dict) else None}
            for e in tool_data_list if e.get("tool") == "get_final_price_tool"
        ],
    )
    # Build goods_no → 할인가(extra_fvr_sale_prc) lookup from any get_final_price_tool
    # calls in this turn. Discovery's Flow B/C invokes get_final_price_tool in
    # parallel for each search result; pairing by `input.goods_no` is the only
    # robust way (parallel completion order is non-deterministic).
    price_map: dict[str, int] = {}
    for entry in _find_entries(tool_data_list, "get_final_price_tool"):
        # base_agent.py populates `args` (line 319); chat.py path uses `input`.
        # Accept both so the mapper works in either invocation path.
        goods_no = (entry.get("args") or entry.get("input") or {}).get("goods_no")
        if not goods_no:
            continue
        price_data = _unwrap(entry)
        if not isinstance(price_data, dict):
            continue
        # Prefer extra_fvr_sale_prc (사용자 실결제 할인가); fall back to sale_prc (정가)
        # only if discount price missing/0.
        price = int(_get_num(price_data, "extra_fvr_sale_prc", default=0))
        if not price:
            price = int(_get_num(price_data, "sale_prc", default=0))
        if price:
            price_map[goods_no] = price

    items, metadata = [], []
    for entry in _find_entries(tool_data_list, "search_product_tool", "get_products_recommendations_tool"):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            goods_no = _get_str(row, "goods_no")
            goods_nm = _get_str(row, "goods_nm", "title")
            tire_size = _get_str(row, "tire_size_1", "tire_size_2")
            title = f"{goods_nm} {tire_size}".strip() if tire_size else goods_nm
            # Price priority: matched get_final_price_tool result > inline row field.
            price = price_map.get(goods_no) or int(_get_num(row, "price", "extra_fvr_sale_prc", default=0))
            # Tag chips: prc_grd_nm → primary 강조, goods_pfm_nm → secondary 일반.
            # 빈 값은 칩에서 제외 (FE 가 빈 chip 그리지 않게).
            tags: list[dict] = []
            prc_grd = _get_str(row, "prc_grd_nm")
            if prc_grd:
                tags.append({"text": prc_grd, "primary": True})
            goods_pfm = _get_str(row, "goods_pfm_nm")
            if goods_pfm:
                tags.append({"text": goods_pfm, "primary": False})
            items.append({
                "imageUrl": _get_str(row, "image_url"),
                "title": title,
                "tires": "",
                "price": price,
                "rate": float(_get_num(row, "rate", "rating_avg", default=0.0)),
                "totalQuantity": int(_get_num(row, "totalQuantity", "total_qty", default=0)),
                "tags": tags,
                "description": "",
            })
            metadata.append({"goodsId": goods_no})
    if not items:
        return None
    items, metadata = items[:10], metadata[:10]
    # Mirror LocationTemplate.isBookingFlow — driven purely by goal_type since
    # product cards don't co-occur with the inventory/schedule signal tools.
    # When the active goal is checklist-driven (stock/order/price), a click on
    # a product card should advance the flow (qty → shop → tool call), so the
    # FE must route to /chat instead of /append.
    return _build_event(
        "product",
        {
            "products": items,
            "metadata": metadata,
            "isBookingFlow": _is_goal_booking_followup(),
        },
        assistant_text,
        len(items),
    )


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
                # Persist front/rear tire sizes alongside the car identifier so
                # the coordinator's selection-time resolver can recover
                # tire_size from the listCar template metadata when the user
                # later picks a car. Without this, filter_for_context drops
                # car_no as PII and the resolver has no source to match on.
                "tireSize": _get_str(row, "tire_size_fr") or None,
                "tireSizeRe": _get_str(row, "tire_size_re") or None,
            })
    if not items:
        return None
    # 차량이 1대여도 자동 선택하지 않고 listCar 카드를 노출하여 유저가 직접 선택하도록 유도한다.
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


# ── 8. location ─────────────────────────────────────────────────────────────────

def _map_location(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    called_tools = {e.get("tool", "") for e in tool_data_list}
    # Flow 3.5 (빠른 방문) calls store_list + multi_store_schedule and renders a
    # comparison table as `quickReply`, not a `location` card. Defer to LLM.
    if "get_multi_store_schedule_tool" in called_tools:
        return None
    # Flow 3 STEP A calls store_list + store_inventory in the same turn and
    # emits a text-only `quickReply` describing stock status ("매장에 재고가
    # 확인되었습니다…"), not a `location` card with the full list. Defer to LLM.
    if "get_store_inventory_tool" in called_tools:
        return None
    # Flow 3 STEP C / Flow 5.1 (date-specific) → datepick after detail. If
    # `get_store_schedule_tool` ran, the datepick mapper already wins via
    # priority; for `get_store_detail_tool` with a single shop + non-empty
    # slots, the agent emits its own datepick JSON (mapper has no cal_day in
    # response). Don't second-guess by also producing a location card.
    if "get_store_schedule_tool" in called_tools:
        return None

    # Build shop_id → detail map from same-turn `get_store_detail_tool` calls.
    # `get_store_detail_tool` carries the rich fields the list endpoint omits
    # (tel_no, holiday, is_tna_delivery), so when the agent calls both in the
    # same turn — explicitly the "store info / store selection" flow — we merge
    # them into a single richer description. The detail response itself does
    # NOT include shop_id, so we correlate via the tool's input `args.shop_id`.
    detail_by_shop_id: dict[str, dict] = {}
    for entry in _find_entries(tool_data_list, "get_store_detail_tool"):
        args = entry.get("args") or {}
        shop_id = _get_str(args, "shop_id") if isinstance(args, dict) else ""
        if not shop_id:
            continue
        raw = _unwrap(entry)
        if isinstance(raw, dict):
            detail_by_shop_id[shop_id] = raw

    items, metadata = [], []
    for entry in _find_entries(tool_data_list, "get_store_list_tool", "get_nearby_stores_tool"):
        raw = _unwrap(entry)
        if not isinstance(raw, dict):
            continue
        stores = raw.get("stores")
        if not isinstance(stores, list):
            continue
        for row in stores:
            if not isinstance(row, dict):
                continue
            shop_id = _get_str(row, "shop_id")
            if not shop_id:
                continue

            detail = detail_by_shop_id.get(shop_id, {})

            road_base = _get_str(row, "road_addr_base")
            road_dtl = _get_str(row, "road_addr_dtl")
            road_full = " ".join(p for p in [road_base, road_dtl] if p).strip()
            detail_addr = road_full or _get_str(row, "addr_base", "addr_dtl")

            # Detail endpoint overrides the list endpoint where overlapping (it
            # is the more authoritative source for is_all_my_t / is_installable
            # at lookup time).
            is_all_my_t = bool(detail.get("is_all_my_t", row.get("is_all_my_t", False)))
            is_installable = bool(detail.get("is_installable", row.get("is_installable", False)))
            is_tna_delivery = bool(detail.get("is_tna_delivery", False))

            biz_strt_wday = _get_str(detail, "shop_biz_strt_wday") or _get_str(row, "shop_biz_strt_wday")
            biz_end_wday = _get_str(detail, "shop_biz_end_wday") or _get_str(row, "shop_biz_end_wday")
            biz_wday = f"{biz_strt_wday}~{biz_end_wday}" if biz_strt_wday and biz_end_wday else ""

            biz_strt_time = _normalize_time(_get_str(detail, "shop_biz_strt_time") or _get_str(row, "shop_biz_strt_time"))
            biz_end_time = _normalize_time(_get_str(detail, "shop_biz_end_time") or _get_str(row, "shop_biz_end_time"))
            sat_strt_time = _normalize_time(_get_str(detail, "shop_sat_strt_time") or _get_str(row, "shop_sat_strt_time"))
            sat_end_time = _normalize_time(_get_str(detail, "shop_sat_end_time") or _get_str(row, "shop_sat_end_time"))
            biz_weekday_str = f"평일 {biz_strt_time}~{biz_end_time}" if biz_strt_time and biz_end_time else ""
            biz_sat_str = f"토요일 {sat_strt_time}~{sat_end_time}" if sat_strt_time and sat_end_time else ""
            biz_hours = " / ".join(p for p in [biz_weekday_str, biz_sat_str] if p)

            tel_no = _get_str(detail, "tel_no")
            holiday = _get_str(detail, "holiday")

            services: list[str] = []
            if is_all_my_t:
                services.append("올마이T")
            services.append("온라인 장착 가능" if is_installable else "온라인 장착 불가")
            if is_tna_delivery:
                services.append("T바로배송")
            services_text = " | ".join(services)

            description_lines: list[str] = []
            if road_full:
                description_lines.append(f"📍 {road_full}")
            if biz_wday:
                description_lines.append(f"영업일: {biz_wday}")
            if biz_hours:
                description_lines.append(f"영업시간: {biz_hours}")
            if holiday:
                description_lines.append(f"휴무일: {holiday}")
            if tel_no:
                description_lines.append(f"전화: {tel_no}")
            if services_text:
                description_lines.append(f"서비스: {services_text}")
            description = "\n ".join(description_lines)

            distance_km = row.get("distance_km")
            distance_str = f"{distance_km:.1f}km" if isinstance(distance_km, (int, float)) else ""

            # `todayInstall` is the today-only variant of stock availability.
            # The list endpoint cannot tell us; the detail endpoint signals it
            # only indirectly via `available_slots` for cal_day=TODAY. Leave
            # False — over-claiming "today install" is worse than understating.
            items.append({
                "nameAddress": _get_str(detail, "shop_nm") or _get_str(row, "shop_nm", default=shop_id),
                "distance": distance_str,
                "detailAddress": detail_addr,
                "isAllMyT": is_all_my_t,
                "todayInstall": False,
                "tnaDelivery": is_tna_delivery,
                "description": description,
            })
            metadata.append({"shopId": shop_id})

    if not items:
        return None
    items, metadata = items[:10], metadata[:10]

    # `isBookingFlow` controls FE click routing (True → /chat to advance the
    # flow; False → /append, just renders the description bubble). True when
    # either: (a) this turn explicitly carries a transactional signal —
    # inventory, schedule, price, cart, or order tool ran together with the
    # store list; or (b) the request-scoped goal_type is one of
    # store_with_stock / place_order / price_inquiry, meaning a downstream
    # tool call must follow the user's pick even if that tool didn't run in
    # this turn (e.g., inventory check fires AFTER store selection).
    # Pure Flow 4/5 info lookups with no goal still stay False so clicking a
    # card surfaces the rich description without spuriously advancing.
    is_booking_flow = (
        bool(called_tools & _BOOKING_SIGNAL_TOOLS) or _is_goal_booking_followup()
    )

    short = _summarize(assistant_text, "location", len(items))
    return {
        "type": "data",
        "template": "location",
        "data": {
            "stores": items,
            "metadata": metadata,
            "isBookingFlow": is_booking_flow,
            "assistantResponse": short,
        },
    }


# ── 9. datepick ─────────────────────────────────────────────────────────────────

def _parse_tm_to_hour(tm: str) -> int | None:
    """Parse a BE `tm` slot value to an integer hour (0-23).

    BE OpenAPI spec says `tm` is `HHMM` (e.g. "0900", "1030"), but observed
    runtime payloads also send hour-only ("13"). Accept both, return the hour
    portion. Returns None for unparseable / out-of-range values.
    """
    s = (tm or "").strip()
    if not s.isdigit():
        return None
    if len(s) <= 2:
        h = int(s)
    elif len(s) == 4:
        h = int(s[:2])
    else:
        return None
    return h if 0 <= h <= 23 else None


def _map_datepick(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Map `get_store_schedule_tool` output to a `datepick` event.

    BE response shape (per StoreScheduleResponse in tstation-be-openapi.json):
        {
          "shop_id": "...", "shop_nm": "...", "mode": "...",
          "is_installable": bool, "is_tna_delivery": bool,
          "slots": [{"cal_day": "YYYYMMDD", "tm": "HHMM"}, ...]
        }

    Slots are flat (one entry per available time), not grouped by day. Group by
    `cal_day` and dedupe to integer hours for the FE `availableTimes` contract.
    `get_store_detail_tool` is intentionally skipped — its response does not
    include cal_day, and reconstructing it from input args is not currently
    supported by BaseAgent's tool-result accumulator.
    """
    entries = _find_entries(tool_data_list, "get_store_schedule_tool")
    if not entries:
        return None
    raw = _unwrap(entries[-1])
    if not isinstance(raw, dict):
        return None

    shop_id = _get_str(raw, "shop_id")
    slots = raw.get("slots")
    if not shop_id or not isinstance(slots, list):
        return None

    # Response-level installable flag: when False, treat as no available times
    # (BE may still echo cal_day rows in some modes; FE expects empty list).
    is_installable = bool(raw.get("is_installable", True))

    # Group slots by cal_day, dedupe to hour integers. BE returns ascending,
    # but we sort cal_day strings before emitting to avoid relying on that.
    by_day: dict[str, set[int]] = {}
    for s in slots:
        if not isinstance(s, dict):
            continue
        cal_day = _get_str(s, "cal_day")
        hour = _parse_tm_to_hour(_get_str(s, "tm"))
        if not cal_day or hour is None:
            continue
        bucket = by_day.setdefault(cal_day, set())
        if is_installable:
            bucket.add(hour)

    if not by_day:
        return None

    dates: list[dict] = []
    selected_idx: int | None = None
    for i, cal_day in enumerate(sorted(by_day.keys())):
        times = sorted(by_day[cal_day])
        available = bool(times)
        dates.append({
            "date": _yyyymmdd_to_korean_date(cal_day),
            "available": available,
            "availableTimes": times,
            "index": i,
        })
        if selected_idx is None and available:
            selected_idx = i

    # All days empty → let the LLM emit the "no slots" friendly quickReply
    # ("현재 예약 가능한 시간이 없어요. 다른 날짜를 확인해 보시겠어요?").
    if selected_idx is None:
        return None

    short = _summarize(assistant_text, "datepick", len(dates))
    return {
        "type": "data",
        "template": "datepick",
        "data": {
            "dates": dates,
            "selectedDate": selected_idx,
            "metadata": {"shopId": shop_id},
            "assistantResponse": short,
        },
    }


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
    "location": "고객님, 매장 {n}곳을 안내드립니다. 원하시는 매장을 선택해 주세요.",
    "datepick": "예약 가능한 날짜와 시간을 선택해 주세요.",
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
    "get_store_list_tool": _map_location,
    "get_nearby_stores_tool": _map_location,
    "get_store_schedule_tool": _map_datepick,
}


def try_build_template(accumulated_tool_data: list[dict], assistant_text: str) -> dict | None:
    """Try to build a template event from accumulated tool data using code mapping.

    Returns a template event dict if a code mapper handled it, or None to fall through
    to the LLM UI Template Agent.
    """
    if not accumulated_tool_data:
        return None

    # When multiple tools are called, pick the most important UI template.
    # Priority order is intentional:
    #   datepick > product > listCar > voucher > cheapestProduct > previewYoutube
    #   > qnaComplete > location
    # - datepick is the terminal step in store-stock/booking flows; if the agent
    #   produced a schedule in this turn, that's the answer (regardless of any
    #   earlier store_list call this turn).
    # - location is intermediate (user still has to pick a store), so it sits at
    #   the bottom — almost any other mapped tool that ran in the same turn
    #   represents a more advanced step.
    # - This also handles: get_my_cars → get_products_recommendations →
    #   compare_discount, where product cards should be shown, not
    #   cheapestProduct.
    _PRIORITY = [
        ("get_store_schedule_tool", _map_datepick),
        ("search_product_tool", _map_product),
        ("get_products_recommendations_tool", _map_product),
        ("get_my_cars_tool", _map_list_car),
        ("get_user_vehicles_tool", _map_list_car),
        ("get_available_coupons_tool", _map_voucher),
        ("get_my_coupons_tool", _map_voucher),
        ("compare_discount_tool", _map_cheapest_product),
        ("search_youtube_video_tool", _map_preview_youtube),
        ("transfer_to_qna_tool", _map_qna_complete),
        ("get_nearby_stores_tool", _map_location),
        ("get_store_list_tool", _map_location),
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
