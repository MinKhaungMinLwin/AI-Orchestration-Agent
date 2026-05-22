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
import re
from typing import Any

from services.tstation.common.cta_urls import CTAUrls

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

# Per-request pending_intent, set by the chat service before agent.stream() runs.
# Used by _map_location to detect order/stock flows that arrive via casual conversation
# rather than the formal goal checklist (where goal_type would already be set).
current_pending_intent: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_pending_intent", default=None
)

# True only for turns where the user explicitly asks for normal tire vs run-flat
# price/additional-cost comparison. Prevents generic cheapest/discount compare
# turns from being hijacked just because the candidate set contains RUNFLAT.
current_runflat_comparison: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "current_runflat_comparison", default=False
)

# True only for turns where the user asks whether a regular/named tire is
# suitable for an EV or why an EV-dedicated tire should be used. In that case
# the answer is an explanation/comparison, not a generic product-card list.
current_ev_suitability_comparison: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "current_ev_suitability_comparison", default=False
)

# True when the current turn is triggered by a return-visit CTA chip
# ("<지역> 매장 다시 이용하기" / "<지역>점 다시 이용하기"). Forces isBookingFlow=True
# on the resulting location card so the FE click handler routes to /chat (not
# /append), enabling product/quantity continuation after store selection.
current_return_visit_store_flow: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "current_return_visit_store_flow", default=False
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
    "get_newest_products_tool": "product",
    "get_products_recommendations_tool": "product",
    "get_best_selling_products_tool": "product",
    # listCar
    "get_my_cars_tool": "listCar",
    "get_user_vehicles_tool": "listCar",
    # voucher
    "get_my_coupons_tool": "voucher",
    # qnaComplete
    "transfer_to_qna_tool": "qnaComplete",
    # cheapestProduct
    "compare_discount_tool": "cheapestProduct",
    "get_cheapest_price_tool": "cheapestProduct",
    # event — FE에 event 렌더러 없음, LLM fallback
    # "get_events_tool": "event",
    # previewYoutube
    "search_youtube_video_tool": "previewYoutube",
    # location
    "search_stores_tool": "location",
    "get_store_list_tool": "location",
    "get_nearby_stores_tool": "location",
    "transaction_store_preview_tool": "location",
    "get_stores_with_time_filter_tool": "location",
    "get_favorite_stores_tool": "location",
    # datepick
    "get_store_schedule_tool": "datepick",
    # orderComplete (cart-save / quick-order — terminal step in transaction flow)
    "save_to_cart_tool": "orderComplete",
    "quick_order_tool": "orderComplete",
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
    "transaction_store_preview_tool",
})

# Korean short weekday labels used for datepick `date` strings.
_WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")

_MY_COUPON_LINK = {
    "pc": CTAUrls.MY_COUPON_LIST_PC,
    "mobile": CTAUrls.MY_COUPON_LIST_MOBILE,
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


def _normalize_brand_name(value: str) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def _inventory_shop_ids(raw_inventory: object, key: str) -> set[str]:
    """Extract shop IDs from inventory arrays such as todayShopArray/tnaShopArray."""
    if not isinstance(raw_inventory, dict):
        return set()
    rows = raw_inventory.get(key)
    if not isinstance(rows, list):
        return set()
    ids: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            shop_id = _get_str(row, "shopId", "shop_id")
            if shop_id:
                ids.add(shop_id)
    return ids


def _find_entries(tool_data_list: list[dict], *tool_names: str) -> list[dict]:
    """Filter accumulated_tool_data by tool name; skip error-status entries.

    Tool wrappers emit `{"status": "error", "http_status": ..., ...}` on failure
    (e.g. BE 404). Without this filter, downstream mappers fall through to
    `_unwrap` which returns the error dict as-is, and the mapper produces a
    placeholder row with all-empty fields — visible to the user as a blank
    card next to real results.
    """
    out: list[dict] = []
    for e in tool_data_list:
        if e.get("tool", "") not in tool_names:
            continue
        data = e.get("data")
        if isinstance(data, dict) and data.get("status") == "error":
            continue
        out.append(e)
    return out


_LOCATION_SELECTION_TEXT_RE = re.compile(
    r"원하시는\s*매장|매장을?\s*선택|선택해\s*주세요|골라\s*주세요|"
    r"매장\s*\d+\s*곳",
    re.IGNORECASE,
)


def _looks_like_location_selection_prompt(text: str | None) -> bool:
    return bool(text and _LOCATION_SELECTION_TEXT_RE.search(text))


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


def _format_phone(s: str) -> str:
    """Format a Korean landline/mobile phone number for display.

    BE returns ``tel_no`` as raw digits (e.g. ``"0313810285"``); the FE bubble
    looks much nicer with hyphenated form. Returns the original string when
    the digit count doesn't match a known pattern so we never garble already-
    formatted input or international numbers we don't recognise.
    """
    digits = "".join(c for c in (s or "") if c.isdigit())
    if not digits:
        return ""
    if digits.startswith("02"):
        if len(digits) == 10:
            return f"02-{digits[2:6]}-{digits[6:]}"
        if len(digits) == 9:
            return f"02-{digits[2:5]}-{digits[5:]}"
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return s


# ── 1. product ──────────────────────────────────────────────────────────────────

# Tag chip 매핑 (BE → FE)
# - primary chip (chatbox-product-tag-primary): prc_grd_nm 화이트리스트만 통과.
#   BE 가 이미 한글로 저장 (PR_GOODS_BASE.PRC_GRD_NM) → 그대로 노출.
# - secondary chip (chatbox-product-tag-secondary): goods_pfm_nm 영문 코드를
#   한글 라벨로 매핑. 매핑되지 않은 코드는 chip skip.
_PRC_GRD_ALLOWED: frozenset[str] = frozenset({"프리미엄+", "프리미엄", "스탠다드", "이코노미"})
# `프리미엄+` (플래그십)·`프리미엄` (고급) 두 등급은 FE chip 에서 동일하게 "프리미엄" 으로 노출.
# BE 원본(`prc_grd_nm`)은 그대로 두고 표시 라벨만 통일.
_PRC_GRD_DISPLAY: dict[str, str] = {"프리미엄+": "프리미엄"}
_GOODS_PFM_LABELS: dict[str, str] = {
    "COMFORT": "정숙/승차감",
    "SPORT": "고속/제동성",
    "RUNFLAT": "런플랫",
}


def _map_product(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    # Build goods_no → 회원 결제가 lookup from any get_final_price_tool calls in
    # this turn. Discovery's Flow B/C invokes get_final_price_tool in parallel
    # for each search result; pairing by `input.goods_no` is the only robust
    # way (parallel completion order is non-deterministic).
    #
    # Price priority: cheapest_final_prc (회원 보유 쿠폰 적용 후 최저가, 사이트
    # 결제 페이지와 일치) → extra_fvr_sale_prc (사이트 일반 노출 혜택가, "모든
    # 쿠폰 적용 가정") → sale_prc (정가). cheapest_final_prc 가 non-null 이면
    # 무조건 그것을 써야 결제 카드 paymentAmount 가 사이트와 일치한다.
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
        price = int(_get_num(price_data, "cheapest_final_prc", default=0))
        if not price:
            price = int(_get_num(price_data, "extra_fvr_sale_prc", default=0))
        if not price:
            price = int(_get_num(price_data, "sale_prc", default=0))
        if price:
            price_map[goods_no] = price

    items, metadata = [], []
    # 회원 보유 쿠폰이 적용된 상품이 1건이라도 있으면 응답 말미에 안내 추가.
    has_cheapest_applied = False
    for entry in _find_entries(
        tool_data_list,
        "search_product_tool",
        "get_newest_products_tool",
        "get_products_recommendations_tool",
        "get_best_selling_products_tool",
    ):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            applied_coupons = row.get("cheapest_applied_coupons")
            if isinstance(applied_coupons, list) and applied_coupons:
                has_cheapest_applied = True
            goods_no = _get_str(row, "goods_no")
            goods_nm = _get_str(row, "goods_nm", "title")
            tire_size = _get_str(row, "tire_size_1", "tire_size_2")
            title = f"{goods_nm} {tire_size}".strip() if tire_size else goods_nm
            # Price priority: matched get_final_price_tool result > inline row
            # field (cheapest_final_prc > price/extra_fvr_sale_prc fallback).
            # cheapest_final_prc 는 BE 가 enrich 한 회원 보유 쿠폰 적용 후 최저가 —
            # 사이트 결제 페이지와 일치한다. 없으면 사이트 노출가로 fallback.
            price = (
                price_map.get(goods_no)
                or int(_get_num(row, "cheapest_final_prc", default=0))
                or int(_get_num(row, "price", "extra_fvr_sale_prc", default=0))
            )
            original_price = int(_get_num(row, "sale_prc", default=0)) or None
            discount_rate = float(_get_num(row, "extra_fvr_sale_per", default=0.0)) or None
            discount_amount = (
                original_price - price
                if original_price and price and original_price > price
                else None
            )
            # Tag chips:
            # - primary: prc_grd_nm 화이트리스트 (한글 그대로). 그 외 값은 skip.
            # - secondary: goods_pfm_nm 영문 코드 → 한글 라벨 매핑. 매핑 외 코드는 skip.
            # 각 chip 의 primary 플래그는 FE 클래스 결정 (위치 무관) — primary 누락 시
            # secondary 가 primary 로 보일 일 없음.
            tags: list[dict] = []
            prc_grd = _get_str(row, "prc_grd_nm")
            if prc_grd in _PRC_GRD_ALLOWED:
                tags.append({"text": _PRC_GRD_DISPLAY.get(prc_grd, prc_grd), "primary": True})
            goods_pfm_code = _get_str(row, "goods_pfm_nm").upper()
            goods_pfm_label = _GOODS_PFM_LABELS.get(goods_pfm_code)
            if goods_pfm_label:
                tags.append({"text": goods_pfm_label, "primary": False})
            items.append({
                "imageUrl": _get_str(row, "image_url"),
                "title": title,
                "tires": "",
                "titleProductName": goods_nm,
                "titleTires": tire_size,
                "brandName": _normalize_brand_name(_get_str(row, "brand_nm")),
                "oeBadgeYn": _get_str(row, "oe_badge_yn"),
                "oeMaker": _get_str(row, "t_oe_maker_1"),
                "comfort": "",
                "price": price,
                "originalPrice": original_price,
                "discountRate": discount_rate,
                "discountAmount": discount_amount,
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
    short, response_source = _summarize_with_source(assistant_text, "product", len(items))

    # 회원 보유 쿠폰 적용된 상품이 1건 이상이면 결정적으로 안내 문구 추가.
    # _summarize_with_source 의 첫 문장 컷팅 뒤에 붙여서 truncation 회피.
    _COUPON_FOOTNOTE = "*해당 혜택가는 현재 보유 쿠폰 기준으로 적용된 가격입니다."
    if has_cheapest_applied and _COUPON_FOOTNOTE not in short:
        short = f"{short.rstrip()}\n\n{_COUPON_FOOTNOTE}" if short else _COUPON_FOOTNOTE

    return {
        "type": "data",
        "template": "product",
        "data": {
            "products": items,
            "metadata": metadata,
            "isBookingFlow": _is_goal_booking_followup(),
            "assistantResponse": short,
        },
        "assistant_response_source": response_source,
    }


def inject_product_tags_and_sanitize(
    data_event: dict | None,
    accumulated_tool_data: list[dict],
) -> None:
    """LLM-driven product event 후처리: tags 결정형 주입 + 알수없는 필드 strip.

    LLM 이 OUTPUT_TEMPLATE 을 통해 fenced JSON 으로 product 템플릿을 직접
    emit 하는 경로 (`base_agent._build_data_event_from_text`) 에서, tags 는
    BE row 에서 결정되어야 하므로 매퍼와 동일 규칙으로 덮어쓰고, comfort 같은
    스키마 외 hallucinated 필드는 제거한다.

    Mutation in place. data_event 가 product 템플릿이 아니면 no-op.
    """
    if not isinstance(data_event, dict) or data_event.get("template") != "product":
        return
    data = data_event.get("data")
    if not isinstance(data, dict):
        return
    products = data.get("products")
    metadata = data.get("metadata")
    if not isinstance(products, list):
        return

    # Build goodsId → BE row lookup from accumulated tool data
    rows_by_goods: dict[str, dict] = {}
    for entry in _find_entries(
        accumulated_tool_data,
        "search_product_tool",
        "get_newest_products_tool",
        "get_products_recommendations_tool",
        "get_best_selling_products_tool",
    ):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            goods_no = _get_str(row, "goods_no")
            if goods_no:
                rows_by_goods[goods_no] = row

    # Allowed keys derived from ProductItem schema (single source of truth).
    # Lazy import — avoid template_mapper ↔ schemas circular imports at module load.
    from services.tstation.agents.templates.schemas import ProductItem
    allowed_keys = frozenset(ProductItem.model_fields.keys())

    meta_list = metadata if isinstance(metadata, list) else []
    for i, product in enumerate(products):
        if not isinstance(product, dict):
            continue
        # Strip unknown keys (LLM hallucinations like comfort)
        for key in list(product.keys()):
            if key not in allowed_keys:
                product.pop(key, None)
        # Inject deterministic tags from BE row matched by metadata[i].goodsId.
        meta = meta_list[i] if i < len(meta_list) and isinstance(meta_list[i], dict) else {}
        goods_id = meta.get("goodsId")
        row = rows_by_goods.get(goods_id) if isinstance(goods_id, str) else None
        tags: list[dict] = []
        if row is not None:
            prc_grd = _get_str(row, "prc_grd_nm")
            if prc_grd in _PRC_GRD_ALLOWED:
                tags.append({"text": _PRC_GRD_DISPLAY.get(prc_grd, prc_grd), "primary": True})
            goods_pfm_code = _get_str(row, "goods_pfm_nm").upper()
            goods_pfm_label = _GOODS_PFM_LABELS.get(goods_pfm_code)
            if goods_pfm_label:
                tags.append({"text": goods_pfm_label, "primary": False})
            product["titleProductName"] = _get_str(row, "goods_nm", "title")
            product["titleTires"] = _get_str(row, "tire_size_1", "tire_size_2")
            product["brandName"] = _normalize_brand_name(_get_str(row, "brand_nm"))
            product["oeBadgeYn"] = _get_str(row, "oe_badge_yn")
            product["oeMaker"] = _get_str(row, "t_oe_maker_1")
        product["tags"] = tags


# ── 2. listCar ──────────────────────────────────────────────────────────────────

def _map_list_car(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    # Maintenance D-day flow guard: when get_maintenance_dday_tool ran in the
    # same turn, get_my_cars_tool was used only to map car_no → mbr_car_reg_seq.
    # Emitting a listCar card here would duplicate the vehicle list next to
    # the D-day answer; suppress so quickReply owns the turn.
    if _find_entries(tool_data_list, "get_maintenance_dday_tool"):
        return None
    # Recommendation-entry guard: when the same turn already used
    # get_my_cars_tool only to recover car_lnc_cd / tire_size for
    # get_products_recommendations_tool, a zero-result recommendation should
    # fall through to the agent's quickReply guidance instead of re-showing the
    # exact same vehicle card. Successful recommendation turns are handled by
    # the higher-priority product mapper above, so suppressing here is safe.
    if _find_entries(tool_data_list, "get_products_recommendations_tool"):
        return None
    # Generic advice guard: Discovery sometimes calls get_my_cars_tool only to
    # ground an answer about the user's vehicle ("내차는 트럭인데..." etc.) without
    # actually asking the user to choose one car. In those turns, re-rendering
    # the full vehicle list is misleading noise. Only render listCar when the
    # assistant text clearly asks the user to pick / confirm a vehicle.
    text = (assistant_text or "").strip()
    if text and not any(
        needle in text
        for needle in (
            "선택",
            "골라",
            "어떤 차량",
            "이 차량으로 진행",
            "차량을 확인해",
            "등록된 차량",
            "차량 목록",
        )
    ):
        return None
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
            car_nm = _get_str(row, "car_model_det", "car_nm")
            car_maker = _get_str(row, "car_maker")
            car_info = f"{car_maker} {car_nm}" if car_maker and car_nm else (car_nm or car_maker)
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
    for entry in _find_entries(tool_data_list, "get_my_coupons_tool"):
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
                "dateVoucher": _get_str(row, "use_end_dtime").split(" ")[0],
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
    # 두 도구를 모두 처리: compare_discount_tool (기존: cheapest_goods_no 1건) +
    # get_cheapest_price_tool (신규: 회원 보유 쿠폰 3-stage 시뮬레이션, 상품별 1건).
    entries = _find_entries(tool_data_list, "compare_discount_tool", "get_cheapest_price_tool")
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
        # cheapest_goods_no가 있으면 그것만 (compare_discount_tool 경로)
        if cheapest_no and goods_no != cheapest_no:
            continue

        # get_cheapest_price_tool: applied_coupons 에서 stage별 합산
        applied = row.get("applied_coupons")
        if isinstance(applied, list) and applied:
            product_discount = sum(
                int(c.get("discount_amt", 0)) for c in applied
                if isinstance(c, dict) and c.get("stage") == "product"
            )
            coupon_discount = sum(
                int(c.get("discount_amt", 0)) for c in applied
                if isinstance(c, dict) and c.get("stage") in ("payment", "plus")
            )
            final_price = int(_get_num(row, "final_prc", "final_unit_price", default=0))
        else:
            product_discount = int(_get_num(row, "product_discount", default=0))
            coupon_discount = int(_get_num(row, "coupon_discount", default=0))
            final_price = int(_get_num(row, "final_unit_price", "final_prc", default=0))

        items.append({
            "title": _get_str(row, "goods_nm", "title", default=goods_no),
            "originalPrice": int(_get_num(row, "sale_prc", default=0)),
            "quantity": quantity,
            "totalDiscount": int(_get_num(row, "total_discount", default=0)),
            "productDiscount": product_discount,
            "couponDiscount": coupon_discount,
            "finalPrice": final_price,
        })
        metadata.append({"goodsId": goods_no})

    if not items:
        return None
    return _build_event("cheapestProduct", {"cheapestProduct": items, "metadata": metadata}, assistant_text, len(items))


# ── 5.5 run-flat comparison ───────────────────────────────────────────────────

def _is_runflat_product(row: dict) -> bool:
    pfm = _get_str(row, "goods_pfm_nm").upper()
    if pfm == "RUNFLAT":
        return True
    name = _get_str(row, "goods_nm", "title").lower()
    return "런플랫" in name or "runflat" in name or "run-flat" in name


def _map_runflat_price_comparison(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Build a deterministic quickReply table for normal tire vs run-flat price.

    This owns TC-110-style turns where Discovery first searches by size/model,
    verifies both product groups really exist, then calls compare_discount_tool.
    Without this mapper, the generic priority order renders search results as
    product cards and loses the comparison answer.
    """
    if not current_runflat_comparison.get():
        return None

    compare_entries = _find_entries(tool_data_list, "compare_discount_tool")
    if not compare_entries:
        return None

    product_by_goods_no: dict[str, dict] = {}
    for entry in _find_entries(tool_data_list, "search_product_tool", "get_products_recommendations_tool"):
        raw = _unwrap(entry)
        rows = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            goods_no = _get_str(row, "goods_no")
            if goods_no:
                product_by_goods_no[goods_no] = row

    if not product_by_goods_no:
        return None

    compare_raw = _unwrap(compare_entries[-1])
    if not isinstance(compare_raw, dict):
        return None
    price_rows = compare_raw.get("items", [])
    if not isinstance(price_rows, list):
        return None

    rows: list[dict] = []
    for price_row in price_rows:
        if not isinstance(price_row, dict):
            continue
        goods_no = _get_str(price_row, "goods_no")
        product_row = product_by_goods_no.get(goods_no)
        if not product_row:
            continue
        final_unit_price = int(_get_num(price_row, "final_unit_price", default=0))
        if not final_unit_price:
            continue
        rows.append({
            "goods_no": goods_no,
            "goods_nm": _get_str(product_row, "goods_nm", "title", default=goods_no),
            "tire_size": _get_str(product_row, "tire_size_1", "tire_size_2"),
            "is_runflat": _is_runflat_product(product_row),
            "final_unit_price": final_unit_price,
        })

    normal_rows = [row for row in rows if not row["is_runflat"]]
    runflat_rows = [row for row in rows if row["is_runflat"]]
    if not normal_rows or not runflat_rows:
        return None

    # Use the lowest normal tire as the visible baseline for "how much more".
    baseline = min(normal_rows, key=lambda row: row["final_unit_price"])
    display_rows = sorted(
        sorted(normal_rows, key=lambda row: row["final_unit_price"])[:2]
        + sorted(runflat_rows, key=lambda row: row["final_unit_price"])[:2],
        key=lambda row: (row["is_runflat"], row["final_unit_price"]),
    )

    lines = [
        "고객님, 같은 조건에서 일반 타이어와 런플랫 상품이 함께 확인되어 가격을 비교했어요.",
        "",
        "| 상품 | 런플랫 | 1개 기준 최종가 | 일반 타이어 대비 |",
        "|---|---:|---:|---:|",
    ]
    for row in display_rows:
        delta = row["final_unit_price"] - baseline["final_unit_price"]
        if row["goods_no"] == baseline["goods_no"]:
            delta_text = "기준"
        elif delta > 0:
            delta_text = f"+{delta:,}원"
        elif delta < 0:
            delta_text = f"{delta:,}원"
        else:
            delta_text = "동일"
        product = f"{row['goods_nm']} {row['tire_size']}".strip()
        lines.append(
            f"| {product} | {'O' if row['is_runflat'] else 'X'} | {row['final_unit_price']:,}원 | {delta_text} |"
        )
    lines.extend([
        "",
        "런플랫은 보통 일반 타이어보다 비싼 편이지만, 차이는 모델과 사이즈별로 달라요.",
        "",
        "현재 조회된 같은 조건 상품 기준의 비교입니다.",
        "",
        "온라인 주문 기준 무료 배송/무료 장착 정책은 일반 타이어와 런플랫에 동일하게 적용됩니다. 별도 추가 장착비는 확인된 금액이 있을 때만 안내할 수 있어요.",
    ])

    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": [
                {"label": "런플랫 상품 보기", "domain": "DISCOVERY"},
                {"label": "일반 타이어 보기", "domain": "DISCOVERY"},
                {"label": "구매하기", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["DISCOVERY", "TRANSACTION"],
        },
        "assistant_response_source": "code_mapper",
    }


# ── 6. event ────────────────────────────────────────────────────────────────────

def _is_ev_product(row: dict) -> bool:
    car_kind = _get_str(row, "car_knd_nm").lower()
    return "전기차" in car_kind or car_kind == "ev" or "electric" in car_kind


def _display_product_name(row: dict) -> str:
    name = _get_str(row, "goods_nm", "title", default="상품")
    size = _get_str(row, "tire_size_1", "tire_size_2", "tire_size")
    return f"{name} {size}".strip()


def _map_ev_suitability_comparison(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Build a deterministic quickReply for EV tire suitability comparisons."""
    if not current_ev_suitability_comparison.get():
        return None

    rows: list[dict] = []
    seen: set[str] = set()
    for entry in _find_entries(tool_data_list, "search_product_tool", "get_products_recommendations_tool"):
        raw = _unwrap(entry)
        items = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else [])
        if not isinstance(items, list):
            continue
        for row in items:
            if not isinstance(row, dict):
                continue
            key = _get_str(row, "goods_no") or _display_product_name(row)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)

    if not rows:
        return None

    ev_rows = [row for row in rows if _is_ev_product(row)]
    non_ev_rows = [row for row in rows if not _is_ev_product(row)]
    ev_names = [_display_product_name(row) for row in ev_rows[:3]]
    non_ev_names = [_display_product_name(row) for row in non_ev_rows[:3]]

    lines = [
        "고객님 차량이 전기차라면 전기차 전용 타이어를 우선 추천드려요.",
        "",
        "전기차는 차량 중량이 크고 순간 토크가 높아 마모, 정숙성, 승차감, 전비에 최적화된 타이어가 유리합니다.",
    ]
    if ev_names:
        lines.extend([
            "",
            f"현재 조회된 상품 기준으로는 {', '.join(ev_names)} 상품이 전기차용으로 확인되어 더 적합합니다.",
        ])
    else:
        lines.extend([
            "",
            "현재 조회된 상품 중 전기차 전용으로 확인된 상품은 없어 전기차용 추천 상품을 다시 확인해 드리는 것이 좋습니다.",
        ])
    if non_ev_names:
        lines.extend([
            "",
            f"{', '.join(non_ev_names)} 상품도 조건이 맞으면 장착은 검토할 수 있지만, 현재 조회 데이터 기준 전기차 전용 상품으로 확인되지는 않아 1순위 추천은 아닙니다.",
        ])

    return {
        "type": "data",
        "template": "quickReply",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": [
                {"label": "전기차용 타이어 추천", "domain": "DISCOVERY"},
                {"label": "다른 상품 비교", "domain": "DISCOVERY"},
                {"label": "구매하기", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["DISCOVERY", "TRANSACTION"],
        },
        "assistant_response_source": "code_mapper",
    }


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
    short, response_source = _summarize_with_source(assistant_text, "previewYoutube", len(items))
    # previewYoutube: FE reads data.text (not assistantResponse) for intro text
    return {"type": "data", "template": "previewYoutube", "data": {
        "items": items,
        "text": short,
        "assistantResponse": short,
    }, "assistant_response_source": response_source}


# ── 8. location ─────────────────────────────────────────────────────────────────

# 매장 보유 서비스 코드 → 사용자 노출 라벨 매핑.
# 113 (타이어 - 온라인) 은 거의 모든 매장 보유라 노출 생략 (가독성).
# 124/125 (얼라인먼트 오프라인/온라인) 은 사용자 입장에서 동일 의미라 같은 라벨로 통합.
_SVC_CODE_LABELS: dict[str, str] = {
    "116": "배터리",
    "119": "타이어 보관",
    "120": "수입타이어",
    "121": "경정비",
    "122": "경정비 당일",
    "124": "얼라인먼트",
    "125": "얼라인먼트",
    "126": "무상점검",
}


def _svc_code_label_list(svc_codes: object) -> list[str]:
    """svc_codes (list[str]) → 중복 제거된 사용자 라벨 리스트 (입력 순서 유지)."""
    if not isinstance(svc_codes, list):
        return []
    labels: list[str] = []
    seen: set[str] = set()
    for code in svc_codes:
        label = _SVC_CODE_LABELS.get(str(code))
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    return labels


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

    # `transaction_store_preview_tool` with no available schedule. The preview
    # tool runs in purchase flow ("이 상품 N개 [매장/근처] 오늘 가능?"); when its
    # `schedule.tier == "none"` (or `schedule.stores` is empty), today install
    # is unavailable across all candidates. Rendering a location card here is
    # a dead end — clicking any store (isBookingFlow=true) routes back through
    # the same flow that just returned no slot. Emit a quickReply with chips
    # guiding the user to broaden the search or shift the date instead.
    if "transaction_store_preview_tool" in called_tools:
        for entry in _find_entries(tool_data_list, "transaction_store_preview_tool"):
            raw = _unwrap(entry)
            if not isinstance(raw, dict):
                continue
            schedule = raw.get("schedule") if isinstance(raw.get("schedule"), dict) else {}
            schedule_stores = schedule.get("stores") if isinstance(schedule, dict) else None
            schedule_empty = (
                _get_str(schedule, "tier").lower() == "none"
                or (isinstance(schedule_stores, list) and not schedule_stores)
            )
            if not schedule_empty:
                continue
            # DETERMINISTIC GUARD on the tool response (region search or
            # multi-candidate tier=none) — the tool already instructed the
            # agent to STOP and render `location`. Fall through to the
            # location render below so the candidate list reaches the FE.
            if raw.get("instruction_to_agent"):
                break
            # candidate_shop_ids non-empty (single named-store case) means future
            # slots may exist — let the agent call get_store_schedule_tool for a
            # datepick instead of dead-ending here.
            candidate_ids = schedule.get("candidate_shop_ids") or raw.get("candidate_shop_ids") or []
            if candidate_ids:
                return None
            args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
            store_nm = _get_str(args, "store_nm") if isinstance(args, dict) else ""
            short = (assistant_text or "").strip()
            if not short or len(short) > 120:
                short = (
                    f"{store_nm} 기준으로 오늘 장착 가능 일정이 확인되지 않았어요."
                    if store_nm
                    else "근처 매장에서 오늘 장착 가능 일정이 확인되지 않았어요."
                )
            return {
                "type": "data",
                "template": "quickReply",
                "assistant_response_source": "code_mapper",
                "data": {
                    "assistantResponse": short,
                    "quickReplies": [
                        {"label": "다른 매장 찾기", "domain": "TRANSACTION"},
                        {"label": "다른 날짜 확인", "domain": "TRANSACTION"},
                    ],
                    "predictedDomains": ["TRANSACTION"],
                },
            }

    # Flow 5 General — info-only store attribute query (운영시간/주소/전화/휴무일/
    # 서비스 가능 여부/올마이T·T바로배송·수입차 가능 등). When no booking signal
    # ran this turn AND the active goal isn't booking-followup AND isn't list
    # browsing (`store_finder`), the user is asking ABOUT a specific store, not
    # picking one. The agent's text answer carries the response; rendering a
    # single-item clickable card implies a selection action that doesn't exist
    # and risks showing default-False fields (tnaDelivery/todayInstall) as if
    # they were authoritative when the list endpoint simply omits them.
    has_booking_signal = bool(called_tools & _BOOKING_SIGNAL_TOOLS)
    is_list_browsing = current_goal_type.get() == "store_finder"
    # Booking-implying intents that arrived via casual conversation ("구매한다고",
    # "재고 확인해줘", "와이퍼 예약좀") rather than the formal goal checklist.
    # ⚠️ ContextVar holds the raw `PendingIntent` enum value
    # ("price"/"stock"/"order"/"reservation"), NOT the Korean prompt labels
    # ("주문 진행"/"재고 확인"/"방문 예약"). Compare against enum values.
    # "reservation" is included so 매장 방문 예약 (와이퍼/배터리/얼라인먼트 등 부가
    # 서비스 예약 포함) 컨텍스트에서 location 카드가 isBookingFlow=true 로 emit되어
    # FE 매장 클릭이 /chat chain (다음 step datepick) 으로 이어진다.
    has_booking_intent = current_pending_intent.get() in ("order", "stock", "reservation")
    # 단골매장 조회는 사용자가 직접 발화로 요청한 명시적 컨텍스트 — booking signal/
    # intent 가 없어도 항상 카드 노출 (info-only guard 우회). 1건이라도 사용자가
    # 클릭으로 선택해야 다음 단계로 진행됨.
    has_favorite_stores = "get_favorite_stores_tool" in called_tools
    if (
        not has_booking_signal
        and not _is_goal_booking_followup()
        and not is_list_browsing
        and not has_booking_intent
        and not has_favorite_stores
        and not _looks_like_location_selection_prompt(assistant_text)
    ):
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

    stock_filter_context = (
        current_pending_intent.get() == "stock"
        or current_goal_type.get() == "store_with_stock"
        or bool(re.search(r"재고\s*(있는|가\s*확인된)\s*매장|재고있는\s*매장", assistant_text or ""))
    )
    items, metadata = [], []
    stock_filtered_preview = False
    stock_filtered_region = ""
    for entry in _find_entries(tool_data_list, "search_stores_tool", "get_store_list_tool", "get_nearby_stores_tool", "transaction_store_preview_tool", "get_favorite_stores_tool"):
        raw = _unwrap(entry)
        if not isinstance(raw, dict):
            continue
        stores = raw.get("stores")
        if not isinstance(stores, list):
            continue
        stock_labels_by_shop_id: dict[str, str] = {}
        if entry.get("tool") == "transaction_store_preview_tool" and stock_filter_context:
            today_ids = _inventory_shop_ids(raw.get("inventory"), "todayShopArray")
            tna_ids = _inventory_shop_ids(raw.get("inventory"), "tnaShopArray")
            for sid in today_ids:
                stock_labels_by_shop_id[sid] = "매장재고"
            for sid in tna_ids:
                stock_labels_by_shop_id.setdefault(sid, "T바로배송")
            if stock_labels_by_shop_id:
                stock_filtered_preview = True
                args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
                if isinstance(args, dict):
                    stock_filtered_region = _get_str(args, "region_code")

        for row in stores:
            if not isinstance(row, dict):
                continue
            shop_id = _get_str(row, "shop_id")
            if not shop_id:
                continue
            stock_label = stock_labels_by_shop_id.get(shop_id)
            if stock_labels_by_shop_id and not stock_label:
                continue

            detail = detail_by_shop_id.get(shop_id, {})

            road_base = _get_str(row, "road_addr_base")
            road_dtl = _get_str(row, "road_addr_dtl")
            road_full = " ".join(p for p in [road_base, road_dtl] if p).strip()
            # Fallback when no road address — combine base + dtl so the user
            # sees the full address ("경상남도 거창군 거창읍 강남로 72") instead
            # of just the prefecture/gu portion ("경상남도 거창군").
            jibun_base = _get_str(row, "addr_base")
            jibun_dtl = _get_str(row, "addr_dtl")
            jibun_full = " ".join(p for p in [jibun_base, jibun_dtl] if p).strip()
            detail_addr = road_full or jibun_full

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

            # tel_no: prefer detail (most authoritative when get_store_detail_tool
            # ran in the same turn), fall back to the list row so basic store
            # search results always show the phone number.
            tel_no = _get_str(detail, "tel_no") or _get_str(row, "tel_no")
            holiday = _get_str(detail, "holiday")
            rating = _get_num(detail, "rating_idx") or _get_num(row, "rating_idx")

            services: list[str] = []
            if is_all_my_t:
                services.append("올마이T")
            services.append("온라인 장착 가능" if is_installable else "온라인 장착 불가")
            if is_tna_delivery:
                services.append("T바로배송")
            # 매장 보유 svc_codes (BE 화이트리스트: 113/116/119/120/121/122/124/125/126)
            # 를 사용자 라벨로 변환해 description 의 "서비스:" 라인에 노출.
            svc_codes_raw = detail.get("svc_codes") or row.get("svc_codes")
            services.extend(_svc_code_label_list(svc_codes_raw))
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
            if rating:
                description_lines.append(f"⭐ {rating:.1f}")
            if services_text:
                description_lines.append(f"서비스: {services_text}")
            if stock_label:
                description_lines.append(f"[{stock_label}]")
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
                "todayInstall": stock_label == "매장재고",
                "tnaDelivery": is_tna_delivery or stock_label == "T바로배송",
                "description": description,
            })
            metadata.append({"shopId": shop_id})

    if not items:
        return None
    items, metadata = items[:10], metadata[:10]

    # In order context, when the agent calls get_store_list_tool with a
    # `store_nm` arg (user named a specific branch) and gets back exactly 1
    # store, this is a shop_id resolution turn — the user already selected a
    # store from a previously shown list and the agent is resolving the name
    # to an ID before calling inventory/schedule tools. Rendering the card
    # again creates an infinite loop because the FE re-sends the store name
    # on each click. Region-only searches (`region_code=...`) that happen to
    # yield 1 store do NOT loop — the user hasn't named that store yet, so
    # we must render the card for selection.
    called_with_store_nm = False
    for entry in _find_entries(tool_data_list, "search_stores_tool", "get_store_list_tool"):
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        if isinstance(args, dict) and args.get("store_nm"):
            called_with_store_nm = True
            break
    is_shopid_resolution = (
        called_with_store_nm
        and has_booking_intent
        and len(items) == 1
        and "get_nearby_stores_tool" not in called_tools
        and "search_place_tool" not in called_tools
    )
    if is_shopid_resolution:
        return None

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
        bool(called_tools & _BOOKING_SIGNAL_TOOLS)
        or _is_goal_booking_followup()
        or has_booking_intent
        or current_return_visit_store_flow.get()
    )

    short, response_source = _summarize_with_source(assistant_text, "location", len(items))
    if stock_filtered_preview and items:
        short = (
            f"{stock_filtered_region}에서 재고가 확인된 매장입니다. 원하시는 매장을 선택해 주세요."
            if stock_filtered_region
            else "재고가 확인된 매장입니다. 원하시는 매장을 선택해 주세요."
        )
        response_source = "code_mapper"
    return {
        "type": "data",
        "template": "location",
        "assistant_response_source": response_source,
        "data": {
            "stores": items,
            "metadata": metadata,
            "isBookingFlow": is_booking_flow,
            "assistantResponse": short,
        },
    }


def _format_time_filter_slot(slot: object) -> str:
    try:
        return f"{int(slot):02d}:00"
    except (TypeError, ValueError):
        return str(slot)


def _map_time_filter_location(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    for entry in _find_entries(tool_data_list, "get_stores_with_time_filter_tool"):
        raw = _unwrap(entry)
        if not isinstance(raw, dict):
            continue

        stores = raw.get("stores_available")
        if not isinstance(stores, list):
            continue

        region_code = _get_str(raw, "region_code")
        threshold = raw.get("time_threshold_hour")
        kst = datetime.timezone(datetime.timedelta(hours=9))
        today_yyyymmdd = datetime.datetime.now(kst).strftime("%Y%m%d")
        items, metadata = [], []
        for row in stores:
            if not isinstance(row, dict):
                continue
            shop_id = _get_str(row, "shop_id")
            if not shop_id:
                continue

            slots = row.get("qualifying_slots") if isinstance(row.get("qualifying_slots"), list) else []
            slot_text = ", ".join(_format_time_filter_slot(s) for s in slots[:5])
            cal_day_raw = _get_str(row, "cal_day")
            cal_day = _yyyymmdd_to_korean_date(cal_day_raw)
            address = _get_str(row, "address")
            tel = _format_phone(_get_str(row, "tel"))
            rating = _get_num(row, "rating_idx")
            is_all_my_t = bool(row.get("is_all_my_t", False))
            is_tna_delivery = bool(row.get("is_tna_delivery", False))
            today_install = bool(cal_day_raw == today_yyyymmdd and slots)
            description_lines: list[str] = []
            if address:
                description_lines.append(f"📍 {address}")
            if cal_day:
                description_lines.append(f"예약 가능일: {cal_day}")
            if slot_text:
                description_lines.append(f"예약 가능 시간: {slot_text}")
            if tel:
                description_lines.append(f"전화: {tel}")
            if rating:
                description_lines.append(f"⭐ {rating:.1f}")

            items.append({
                "nameAddress": _get_str(row, "shop_nm", default=shop_id),
                "distance": "",
                "detailAddress": address,
                "isAllMyT": is_all_my_t,
                "todayInstall": today_install,
                "tnaDelivery": is_tna_delivery,
                "description": "\n ".join(description_lines),
            })
            metadata.append({"shopId": shop_id})

        if not items:
            return {
                "type": "data",
                "template": "quickReply",
                "assistant_response_source": "code_mapper",
                "data": {
                    "assistantResponse": f"{region_code}에서 {threshold}시 이후 예약 가능한 매장이 현재 없어요. 다른 시간대나 지역으로 찾아드릴까요?",
                    "quickReplies": [
                        {"label": "다른 시간대 찾기", "domain": "TRANSACTION"},
                        {"label": "다른 지역 찾기", "domain": "TRANSACTION"},
                        {"label": "처음으로", "domain": "LEADING"},
                    ],
                    "predictedDomains": ["TRANSACTION"],
                },
            }

        items, metadata = items[:10], metadata[:10]
        short, response_source = _summarize_with_source(assistant_text, "location", len(items))
        if not assistant_text.strip():
            short = f"{region_code}에서 {threshold}시 이후 예약 가능한 매장 {len(items)}곳을 안내드립니다. 원하시는 매장을 선택해 주세요."
            response_source = "default"
        return {
            "type": "data",
            "template": "location",
            "assistant_response_source": response_source,
            "data": {
                "stores": items,
                "metadata": metadata,
                "isBookingFlow": True,
                "assistantResponse": short,
            },
        }

    return None


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


def _is_bookable_hour(hour: int) -> bool:
    """Return whether a parsed hour may be shown as a selectable booking slot."""
    return hour != 12


def _map_datepick_from_preview(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Build a date picker from transaction_store_preview_tool schedule slots.

    The preview tool can already resolve the only installable store and its
    slots. In booking/order contexts, rendering all candidate stores as a
    location card makes the user pick among stores that may not have matching
    inventory. Keep stock-check contexts on the location path, where the card
    intentionally shows the stock-positive store list.
    """
    for entry in reversed(_find_entries(tool_data_list, "transaction_store_preview_tool")):
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        args = args if isinstance(args, dict) else {}
        exact_order_preview = bool(
            _get_str(args, "store_nm")
            and _get_str(args, "goods_no")
            and args.get("ord_qty")
            and args.get("include_price")
        )
        pending_intent = current_pending_intent.get()
        goal_type = current_goal_type.get()
        if not exact_order_preview and (pending_intent == "stock" or goal_type == "store_with_stock"):
            return None
        if not exact_order_preview and re.search(r"재고\s*(있는|가\s*확인된)\s*매장|재고있는\s*매장", assistant_text or ""):
            return None

        raw = _unwrap(entry)
        if not isinstance(raw, dict):
            continue
        schedule = raw.get("schedule")
        if not isinstance(schedule, dict) or _get_str(schedule, "tier").lower() == "none":
            continue
        stores = schedule.get("stores")
        if not isinstance(stores, list) or len(stores) != 1:
            continue
        store = stores[0]
        if not isinstance(store, dict):
            continue
        shop_id = _get_str(store, "shop_id")
        slots = store.get("slots")
        if not shop_id or not isinstance(slots, list):
            continue

        by_day: dict[str, set[int]] = {}
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            cal_day = _get_str(slot, "cal_day")
            hour = _parse_tm_to_hour(_get_str(slot, "tm"))
            if cal_day and hour is not None:
                bucket = by_day.setdefault(cal_day, set())
                if _is_bookable_hour(hour):
                    bucket.add(hour)
        if not by_day:
            continue

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
        if selected_idx is None:
            continue

        short, response_source = _summarize_with_source(assistant_text, "datepick", len(dates))
        metadata: dict = {"shopId": shop_id}
        shop_nm = _get_str(store, "shop_nm")
        if shop_nm:
            metadata["shopName"] = shop_nm
        return {
            "type": "data",
            "template": "datepick",
            "assistant_response_source": response_source,
            "data": {
                "dates": dates,
                "selectedDate": selected_idx,
                "metadata": metadata,
                "assistantResponse": short,
            },
        }
    return None


def _map_datepick(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Map slot-emitting tools to a `datepick` event.

    Three sources supported:

    1. ``get_store_schedule_tool`` (StoreScheduleResponse):
       ``{shop_id, shop_nm, mode, is_installable, is_tna_delivery,
       slots: [{cal_day, tm}, ...]}`` — flat list grouped by day.

    2. ``get_store_detail_tool`` (Flow 5.1 / 5.5 single-day lookup):
       response has ``available_slots`` (hour strings, e.g. ``["09","10"]``)
       and the ``cal_day`` is taken from the tool's input args. Without this
       path the agent's intended datepick gets overridden by the location
       mapper when a sibling ``transaction_store_preview_tool`` ran.

    3. ``transaction_store_preview_tool`` (single resolved schedule store):
       response has ``schedule.stores[0].slots`` and can go straight to
       datepick in booking/order contexts.

    Schedule-tool path wins when both are present (richer multi-day shape).
    """
    entries = _find_entries(tool_data_list, "get_store_schedule_tool")
    if not entries:
        return _map_datepick_from_preview(tool_data_list, assistant_text) or _map_datepick_from_detail(
            tool_data_list,
            assistant_text,
        )
    raw = _unwrap(entries[-1])
    if not isinstance(raw, dict):
        return _map_datepick_from_preview(tool_data_list, assistant_text) or _map_datepick_from_detail(
            tool_data_list,
            assistant_text,
        )

    shop_id = _get_str(raw, "shop_id")
    shop_nm = _get_str(raw, "shop_nm")
    slots = raw.get("slots")
    if not shop_id or not isinstance(slots, list):
        return _map_datepick_from_preview(tool_data_list, assistant_text) or _map_datepick_from_detail(
            tool_data_list,
            assistant_text,
        )

    # `is_installable` means online-shopping tire installation support. It
    # should block tire/order schedule modes, but not the `general` store-visit
    # schedule where the backend's slots are still the authoritative answer.
    mode = _get_str(raw, "mode").lower()
    allow_slots = bool(raw.get("is_installable", True)) or mode == "general"

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
        if allow_slots and _is_bookable_hour(hour):
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

    short, response_source = _summarize_with_source(assistant_text, "datepick", len(dates))
    metadata: dict = {"shopId": shop_id}
    if shop_nm:
        metadata["shopName"] = shop_nm
    return {
        "type": "data",
        "template": "datepick",
        "assistant_response_source": response_source,
        "data": {
            "dates": dates,
            "selectedDate": selected_idx,
            "metadata": metadata,
            "assistantResponse": short,
        },
    }


def _map_datepick_from_detail(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Build a single-day `datepick` from `get_store_detail_tool` slots.

    Detail-tool response carries ``available_slots`` (hour strings) for one
    cal_day; cal_day itself isn't in the response, so we read it from the
    tool's input args. Falls back to None when args.cal_day is missing or
    slots are empty/unparseable.

    Booking-intent guard: when the same turn carries no booking-signal tool
    (stock/price/cart/order), the user is asking for plain store info, not
    booking a slot. Returning None lets `_map_store_detail_info` render the
    info card instead of an unwanted reservation picker.
    """
    called_tools = {e.get("tool", "") for e in tool_data_list}
    if not (called_tools & _BOOKING_SIGNAL_TOOLS):
        return None
    for entry in _find_entries(tool_data_list, "get_store_detail_tool"):
        args = entry.get("args") if isinstance(entry.get("args"), dict) else entry.get("input")
        if not isinstance(args, dict):
            continue
        cal_day = _get_str(args, "cal_day")
        shop_id = _get_str(args, "shop_id")
        if not cal_day or not shop_id:
            continue
        raw = _unwrap(entry)
        if not isinstance(raw, dict):
            continue
        slot_strs = raw.get("available_slots")
        if not isinstance(slot_strs, list) or not slot_strs:
            continue
        hours: list[int] = []
        for s in slot_strs:
            h = _parse_tm_to_hour(str(s))
            if h is not None and _is_bookable_hour(h):
                hours.append(h)
        hours = sorted(set(hours))
        if not hours:
            continue
        short, response_source = _summarize_with_source(assistant_text, "datepick", 1)
        shop_nm = _get_str(raw, "shop_nm")
        metadata: dict = {"shopId": shop_id}
        if shop_nm:
            metadata["shopName"] = shop_nm
        return {
            "type": "data",
            "template": "datepick",
            "assistant_response_source": response_source,
            "data": {
                "dates": [{
                    "date": _yyyymmdd_to_korean_date(cal_day),
                    "available": True,
                    "availableTimes": hours,
                    "index": 0,
                }],
                "selectedDate": 0,
                "metadata": metadata,
                "assistantResponse": short,
            },
        }
    return None


# ── 10. orderComplete ───────────────────────────────────────────────────────────

def _map_order_complete(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """save_to_cart_tool / quick_order_tool 결과를 orderComplete 카드로 변환.

    cart 흐름은 LLM 의 fenced JSON 생성에 의존하면 종종 누락되어 base_agent 의
    `_VALIDATION_FALLBACK_QUICK_REPLIES` 경로로 빠지면서 ["다시 시도", "상담사 연결",
    "처음으로"] chips 가 사용자에게 노출됐다. 이 mapper 가 결정적으로 카드를
    만들어 fallback 경로 자체를 우회한다.
    """
    entries = _find_entries(tool_data_list, "save_to_cart_tool", "quick_order_tool")
    if not entries:
        return None
    entry = entries[-1]
    flow_type = "cart" if entry.get("tool") == "save_to_cart_tool" else "order"

    args = entry.get("args") if isinstance(entry.get("args"), dict) else {}
    goods_no = _get_str(args, "goods_no")
    if not goods_no:
        return None
    ord_qty = int(_get_num(args, "ord_qty", default=0)) or 1
    shop_id = _get_str(args, "shop_id")
    car_lnc_cd = _get_str(args, "car_lnc_cd")

    raw = _unwrap(entry)
    is_success = bool(raw.get("result")) if isinstance(raw, dict) else False
    outer = entry.get("data") if isinstance(entry.get("data"), dict) else {}
    if outer.get("status") == "error":
        is_success = False

    ord_no: str | None = None
    if isinstance(raw, dict):
        inner = raw.get("data")
        if isinstance(inner, str) and inner.strip():
            ord_no = inner.strip()
        elif isinstance(inner, dict):
            ord_no = _get_str(inner, "ord_no", "ordNo") or None

    # Enrich product label from same-turn product/recommend/cheapest tool data.
    # 사용자 노출용이라 goods_no 는 표기하지 않고 "goods_nm tire_size" 로만 보여준다.
    goods_nm = ""
    tire_size = ""
    for product_entry in _find_entries(
        tool_data_list,
        "search_product_tool",
        "get_products_recommendations_tool",
        "get_best_selling_products_tool",
        "compare_discount_tool",
    ):
        praw = _unwrap(product_entry)
        rows = praw.get("items") if isinstance(praw, dict) else (praw if isinstance(praw, list) else [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and _get_str(row, "goods_no") == goods_no:
                goods_nm = _get_str(row, "goods_nm", "title")
                tire_size = _get_str(row, "tire_size_1", "tire_size_2")
                break
        if goods_nm:
            break
    if goods_nm and tire_size:
        product_label = f"{goods_nm} {tire_size}"
    elif goods_nm:
        product_label = goods_nm
    else:
        product_label = goods_no

    # Enrich carInfo from same-turn vehicle tools (match by car_lnc_cd).
    car_info: str | None = None
    if car_lnc_cd:
        for car_entry in _find_entries(tool_data_list, "get_my_cars_tool", "get_user_vehicles_tool"):
            craw = _unwrap(car_entry)
            if isinstance(craw, list):
                rows = craw
            elif isinstance(craw, dict):
                rows = craw.get("items") if "items" in craw else [craw]
            else:
                rows = []
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict) and _get_str(row, "car_lnc_cd") == car_lnc_cd:
                    car_nm = _get_str(row, "car_model_det", "car_nm")
                    car_no = _get_str(row, "car_no")
                    if car_nm and car_no:
                        car_info = f"{car_nm} ({car_no})"
                    elif car_nm:
                        car_info = car_nm
                    break
            if car_info:
                break

    # Enrich storeName from same-turn store tools (match by shop_id).
    store_name: str | None = None
    if shop_id:
        for store_entry in _find_entries(tool_data_list, "get_store_list_tool", "get_nearby_stores_tool"):
            sraw = _unwrap(store_entry)
            stores = sraw.get("stores") if isinstance(sraw, dict) else []
            if not isinstance(stores, list):
                continue
            for store in stores:
                if isinstance(store, dict) and _get_str(store, "shop_id") == shop_id:
                    shop_nm = _get_str(store, "shop_nm")
                    if shop_nm:
                        store_name = shop_nm
                    break
            if store_name:
                break
        if not store_name:
            for detail_entry in _find_entries(tool_data_list, "get_store_detail_tool"):
                dargs = detail_entry.get("args") if isinstance(detail_entry.get("args"), dict) else {}
                if _get_str(dargs, "shop_id") != shop_id:
                    continue
                draw = _unwrap(detail_entry)
                if isinstance(draw, dict):
                    shop_nm = _get_str(draw, "shop_nm")
                    if shop_nm:
                        store_name = shop_nm
                        break

    # Enrich paymentAmount from same-turn price tool.
    # Definition mirrors transaction_agent.py 최종 금액: (FINAL + wage_prc) × qty.
    payment_amount: int | None = None
    for price_entry in _find_entries(tool_data_list, "get_final_price_tool"):
        praw = _unwrap(price_entry)
        if not isinstance(praw, dict):
            continue
        final_unit = _get_num(praw, "extra_fvr_sale_prc", "final_unit_price", default=0)
        wage = _get_num(praw, "wage_prc", default=0)
        if final_unit:
            payment_amount = int((final_unit + wage) * ord_qty)
            break

    # cart 흐름은 카트 카드 대신 짧은 confirmation 메시지 + 다음 액션 chips
    # ("주문하기" / "처음으로") 만 노출하기로 결정. orderComplete 카드는 quick_order
    # 흐름에서만 사용한다.
    if flow_type == "cart":
        if is_success:
            cart_msg = "장바구니에 담았어요. 😊\n\n바로 주문하시겠어요?"
            cart_chips = [
                {"label": "주문하기", "domain": "TRANSACTION"},
                {"label": "처음으로", "domain": "LEADING"},
            ]
        else:
            cart_msg = "장바구니 담기 중 문제가 생겼어요. 다시 시도해 주세요."
            cart_chips = [
                {"label": "다시 시도", "domain": "TRANSACTION"},
                {"label": "처음으로", "domain": "LEADING"},
            ]
        return {
            "type": "data",
            "template": "quickReply",
            "data": {
                "assistantResponse": cart_msg,
                "quickReplies": cart_chips,
            },
        }

    # order (quick_order_tool) 는 기존 orderComplete 카드 그대로 노출.
    default_msg = "주문이 완료되었습니다. 😊" if is_success else "주문 처리 중 문제가 발생했어요. 다시 시도해 주세요."
    text = (assistant_text or "").strip()
    assistant_response = text if text and len(text) <= 120 else default_msg

    if is_success:
        quick_replies = [
            {"label": "주문 내역 확인", "domain": "TRANSACTION"},
            {"label": "배송 상태 확인", "domain": "TRANSACTION"},
            {"label": "처음으로", "domain": "LEADING"},
        ]
    else:
        quick_replies = [
            {"label": "다시 시도", "domain": "TRANSACTION"},
            {"label": "처음으로", "domain": "LEADING"},
        ]

    return {
        "type": "data",
        "template": "orderComplete",
        "data": {
            "assistantResponse": assistant_response,
            "orderInfo": {
                "carInfo": car_info,
                "product": product_label,
                "quantity": ord_qty,
                "storeName": store_name,
                "bookingDateTime": None,
                "paymentAmount": payment_amount,
            },
            "isSuccess": is_success,
            "type": flow_type,
            "message": None if is_success else default_msg,
            "data": {"status": "success" if is_success else "error"},
            "metadata": {
                "ordNo": ord_no,
                "goodsId": goods_no,
                "shopId": shop_id or None,
            },
            "quickReplies": quick_replies,
        },
    }


# ── 11. quickReply (store detail info-only) ────────────────────────────────────

def _map_store_detail_info(tool_data_list: list[dict], assistant_text: str) -> dict | None:
    """Deterministic ``quickReply`` for Flow 5 General single-store info lookup.

    The transaction agent's prompt expects a full text answer in
    ``assistantResponse`` (line 1066-1072 of c_transaction_agent/agent.py) when
    ``get_store_detail_tool`` runs without slot results, but in practice the
    LLM often slips into PROSE-MODE ("매장 상세정보를 확인했어요.") and the
    actual fields never reach the user — only QC catches it. Build the answer
    in code so the response is correct on the first emission and QC has
    nothing to rewrite.

    Skip rules:
    - Schedule tools own their own templates (datepick / multi-store).
    - Booking-signal tools (price, stock, cart, order) own theirs — those
      cases defer to `_map_datepick_from_detail` for the date picker.

    Note: non-empty ``available_slots`` no longer skips info rendering, and
    a future ``cal_day`` no longer defers to the LLM. When the turn carries
    no booking-signal tool the user is asking for plain store info (e.g.
    clicking a card after a Flow 5.5T region/time search) — render the
    deterministic info card regardless of which cal_day was queried.
    """
    called_tools = {e.get("tool", "") for e in tool_data_list}
    if "get_store_schedule_tool" in called_tools or "get_multi_store_schedule_tool" in called_tools:
        return None
    if called_tools & _BOOKING_SIGNAL_TOOLS:
        return None

    entries = _find_entries(tool_data_list, "get_store_detail_tool")
    if not entries:
        return None
    entry = entries[-1]
    raw = _unwrap(entry)
    if not isinstance(raw, dict):
        return None

    shop_nm = _get_str(raw, "shop_nm")
    if not shop_nm:
        return None

    tel_no = _format_phone(_get_str(raw, "tel_no"))
    holiday = _get_str(raw, "holiday")
    biz_wday_start = _get_str(raw, "shop_biz_strt_wday")
    biz_wday_end = _get_str(raw, "shop_biz_end_wday")
    biz_start = _normalize_time(_get_str(raw, "shop_biz_strt_time"))
    biz_end = _normalize_time(_get_str(raw, "shop_biz_end_time"))
    sat_start = _normalize_time(_get_str(raw, "shop_sat_strt_time"))
    sat_end = _normalize_time(_get_str(raw, "shop_sat_end_time"))

    biz_hours = f"{biz_start}~{biz_end}" if biz_start and biz_end else ""
    sat_hours = f"{sat_start}~{sat_end}" if sat_start and sat_end else ""
    # When Saturday has its own line, the weekday line implicitly means Mon-Fri.
    # Otherwise fall back to BE's reported range (e.g. 월요일~일요일 for shops
    # without a separate Saturday schedule).
    if sat_hours:
        biz_wday_label = "평일"
    elif biz_wday_start and biz_wday_end:
        biz_wday_label = f"{biz_wday_start}~{biz_wday_end}"
    else:
        biz_wday_label = "평일"

    lines: list[str] = [f"고객님, {shop_nm} 매장 정보를 안내드릴게요. 😊", ""]
    lines.append(f"• 매장명: {shop_nm}")
    if tel_no:
        lines.append(f"• 전화번호: {tel_no}")
    if biz_hours:
        lines.append(f"• {biz_wday_label} 영업시간: {biz_hours}")
    if sat_hours:
        lines.append(f"• 토요일 영업시간: {sat_hours}")
    if holiday:
        lines.append(f"• 휴무일: {holiday}")
    if "is_all_my_t" in raw:
        lines.append("• 올마이T: 이용 가능" if raw.get("is_all_my_t") else "• 올마이T: 이용 불가")
    if "is_installable" in raw:
        lines.append("• 온라인 장착: 가능" if raw.get("is_installable") else "• 온라인 장착: 불가")
    if "is_tna_delivery" in raw:
        lines.append("• T바로배송: 가능" if raw.get("is_tna_delivery") else "• T바로배송: 불가")
    if "is_imported_car" in raw:
        lines.append("• 수입차 장착: 가능" if raw.get("is_imported_car") else "• 수입차 장착: 불가")

    svc_labels = _svc_code_label_list(raw.get("svc_codes"))
    if svc_labels:
        lines.append(f"• 제공 서비스: {' | '.join(svc_labels)}")

    return {
        "type": "data",
        "template": "quickReply",
        "assistant_response_source": "code_mapper",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": [],
            "predictedDomains": ["TRANSACTION"],
        },
    }


# ── Common builder ──────────────────────────────────────────────────────────────

def _build_event(template: str, data: dict, assistant_text: str, item_count: int) -> dict:
    """Build a type:data event with a concise assistantResponse."""
    short, response_source = _summarize_with_source(assistant_text, template, item_count)
    data["assistantResponse"] = short
    return {
        "type": "data",
        "template": template,
        "data": data,
        "assistant_response_source": response_source,
    }


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
    "orderComplete": "처리되었습니다. 😊",
}


def _summarize(full_text: str, template: str, item_count: int) -> str:
    return _summarize_with_source(full_text, template, item_count)[0]


_BULLET_PATTERN = re.compile(r"\n-\s+\*\*")


def _summarize_with_source(full_text: str, template: str, item_count: int) -> tuple[str, str]:
    """Domain Agent 텍스트에서 첫 문장만 추출하거나, 기본 안내를 반환한다.

    PROSE MODE 도입 후 LLM이 1–2문장의 짧은 prose("...찾았어요. ...선택해 주세요 😊")를
    내보내는데, 첫 문장에서 자르면 후반부 + 마지막 emoji가 사라진다. 길이가 120자
    이하라면 그대로 유지하고, 그보다 길 때만 첫 문장 컷을 적용한다.

    EXCEPTION — product 템플릿 + bullet 패턴(``\\n- **``) 검출 시 전체 텍스트 유지.
    추천 응답 (인트로 + 상품당 1줄 bullet 요약) 은 길이가 120자를 넘기지만 전체가
    의도된 형식이므로 컷 금지. FE 는 markdown bullet 으로 렌더한다.
    """
    text = (full_text or "").strip()
    if not text:
        return _TEMPLATE_DEFAULTS.get(template, "").format(n=item_count), "default"

    if template == "product" and _BULLET_PATTERN.search(text):
        return text, "llm_prose_with_bullets"

    if len(text) <= 120:
        return text, "llm_prose"

    # 길면 첫 문장으로 컷 (줄바꿈 또는 문장 부호 기준)
    for sep in ["\n", ".\n", "!\n", "?\n", ". ", "! ", "? "]:
        idx = text.find(sep)
        if 0 < idx <= 120:
            return text[: idx + 1].strip(), "llm_prose"

    return _TEMPLATE_DEFAULTS.get(template, "").format(n=item_count), "default"


# ── Mapper registry ─────────────────────────────────────────────────────────────

_MAPPERS: dict[str, Any] = {
    "search_product_tool": _map_product,
    "get_newest_products_tool": _map_product,
    "get_products_recommendations_tool": _map_product,
    "get_best_selling_products_tool": _map_product,
    "get_my_cars_tool": _map_list_car,
    "get_user_vehicles_tool": _map_list_car,
    "get_my_coupons_tool": _map_voucher,
    "transfer_to_qna_tool": _map_qna_complete,
    "compare_discount_tool": _map_cheapest_product,
    "get_cheapest_price_tool": _map_cheapest_product,
    # "get_events_tool": _map_event,  # FE에 event 렌더러 없음
    "search_youtube_video_tool": _map_preview_youtube,
    "search_stores_tool": _map_location,
    "get_store_list_tool": _map_location,
    "get_nearby_stores_tool": _map_location,
    "transaction_store_preview_tool": _map_location,
    "get_favorite_stores_tool": _map_location,
    "get_stores_with_time_filter_tool": _map_time_filter_location,
    "get_store_schedule_tool": _map_datepick,
    "get_store_detail_tool": _map_store_detail_info,
    "save_to_cart_tool": _map_order_complete,
    "quick_order_tool": _map_order_complete,
}


def try_build_template(accumulated_tool_data: list[dict], assistant_text: str) -> dict | None:
    """Try to build a template event from accumulated tool data using code mapping.

    Returns a template event dict if a code mapper handled it, or None to fall through
    to the LLM UI Template Agent.
    """
    if not accumulated_tool_data:
        return None

    runflat_comparison = _map_runflat_price_comparison(accumulated_tool_data, assistant_text)
    if runflat_comparison is not None:
        return runflat_comparison

    ev_suitability_comparison = _map_ev_suitability_comparison(accumulated_tool_data, assistant_text)
    if ev_suitability_comparison is not None:
        return ev_suitability_comparison

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
        # Cart/order are terminal steps in the transaction flow — when they ran,
        # any other tool in the same turn was preparation (product lookup, store
        # selection, price calc) and the orderComplete card is the answer.
        ("save_to_cart_tool", _map_order_complete),
        ("quick_order_tool", _map_order_complete),
        ("get_store_schedule_tool", _map_datepick),
        # Date-specific detail lookup (Flow 5.1 / 5.5) — `get_store_detail_tool`
        # with args.cal_day + non-empty available_slots is a datepick signal.
        # Must outrank the location mappers below; otherwise a sibling
        # `transaction_store_preview_tool(tier=none)` causes `_map_location` to
        # render a store card instead of the intended time-slot picker.
        ("get_store_detail_tool", _map_datepick),
        ("transaction_store_preview_tool", _map_datepick),
        ("search_product_tool", _map_product),
        ("get_newest_products_tool", _map_product),
        ("get_products_recommendations_tool", _map_product),
        ("get_best_selling_products_tool", _map_product),
        ("get_my_cars_tool", _map_list_car),
        ("get_user_vehicles_tool", _map_list_car),
        ("get_my_coupons_tool", _map_voucher),
        ("compare_discount_tool", _map_cheapest_product),
        ("get_cheapest_price_tool", _map_cheapest_product),
        ("search_youtube_video_tool", _map_preview_youtube),
        ("transfer_to_qna_tool", _map_qna_complete),
        ("get_stores_with_time_filter_tool", _map_time_filter_location),
        ("search_stores_tool", _map_location),
        ("get_nearby_stores_tool", _map_location),
        ("get_store_list_tool", _map_location),
        ("transaction_store_preview_tool", _map_location),
        ("get_favorite_stores_tool", _map_location),
        # Lowest priority — only fires when neither the location card path
        # (info-only `_map_location` returns None) nor any higher-priority
        # template applies. Owns the Flow 5 General single-store info answer.
        ("get_store_detail_tool", _map_store_detail_info),
    ]

    called_tools = {e.get("tool", "") for e in accumulated_tool_data}

    # In product-specific coupon queries both sibling tools serve as data sources,
    # not renderers — let the LLM's quickReply fenced JSON win instead.
    _product_coupon_query = "get_product_promotions_tool" in called_tools

    for tool_name, mapper in _PRIORITY:
        if tool_name in called_tools:
            if _product_coupon_query and tool_name in {"search_product_tool", "get_my_coupons_tool"}:
                continue
            result = mapper(accumulated_tool_data, assistant_text)
            if result:
                logger.debug(
                    "[TEMPLATE_MAPPER] Built '%s' template from %s (skipped UI Template Agent)",
                    result.get("template"),
                    tool_name,
                )
                return result

    return None
