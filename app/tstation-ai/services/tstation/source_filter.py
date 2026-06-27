"""Filter tool outputs to keep only QC-relevant fields before passing to QC Agent.

Reduces token count and prevents Lost-in-the-Middle issues by stripping
fields the QC Agent never needs to verify (images, scores, biz hours, etc.).
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_LIST_ITEMS = 10

# ─── Shared field sets — single source of truth for tools in both dicts ───────
# When BE adds a new field, update the base set here; both QC and CTX pick it up.

_STORE_BASE_FIELDS: set[str] = {
    "shop_id",
    "shop_seq",
    "shop_nm",
    "addr_base",
    "addr_dtl",
    "road_addr_base",
    "road_addr_dtl",
    "tel_no",
    "shop_biz_strt_time",
    "shop_biz_end_time",
    "shop_biz_strt_wday",
    "shop_biz_end_wday",
    "holiday",
    "svc_codes",
    "rating_idx",
    "review_count",
}
_NEARBY_STORE_FIELDS: set[str] = _STORE_BASE_FIELDS | {"distance_km"}
_FAVORITE_STORE_FIELDS: set[str] = _STORE_BASE_FIELDS | {"shop_seq", "favored_at"}
_STORE_DETAIL_FIELDS: set[str] = _STORE_BASE_FIELDS | {"is_all_my_t", "is_installable", "is_tna_delivery"}
_STORE_SCHEDULE_FIELDS: set[str] = {"shop_id", "shop_nm", "mode", "is_installable", "is_tna_delivery", "slots"}

_PRODUCT_WARRANTY_FIELDS: set[str] = {"wrt_tp_cd", "wrt_nm", "is_plus"}
_MY_WARRANTY_FIELDS: set[str] = {
    "wrt_tp_cd", "wrt_nm",
    "wrt_reg_date", "wrt_exp_date",
    "wrt_prgs_stat_cd", "wrt_prgs_stat_nm",
}
_CARD_FIELDS: set[str] = {"iscm_cd", "iscm_nm", "tgt_amt", "months", "payment_type"}

# Orders: CTX adds ord_stat_nm (status label for follow-up turn references)
_ORDER_FIELDS_BASE: set[str] = {
    "ord_no", "goods_no", "goods_nm", "tire_size_1", "tire_size_2", "ord_qty", "sys_reg_dtime",
    "ispt_car_seq", "car_no", "mbr_car_unif_no", "car_lnc_cd", "car_maker", "car_model_det", "car_nm",
    "car_tire_size_fr", "car_tire_size_re",
}
_RESERVATION_FIELDS: set[str] = {
    "ord_no",
    "shop_nm",
    "vst_rsv_dtime",
    "shop_rsv_sct_label",
    "shop_vst_rsv_sts_label",
}

# Recommendation product base — shared by QC and CTX.
# QC adds t_highspd_cd (high-speed tier fact-check label).
# CTX adds tot_scr / comfort / silence / life_span (follow-up scoring references).
_RCMD_BASE_FIELDS: set[str] = {
    "goods_no", "goods_nm", "tire_size_1",
    "sale_prc", "extra_fvr_sale_prc", "extra_fvr_sale_per",
    # 신규 케이스용 점수/속성
    "wet", "t_snow", "t_ice", "t_highspd",
    "t_high_hand_avg", "t_com_sil_avg", "t_com_cvs", "t_milg_cvs",
    "t_wgt_idx", "t_wgt_idx_kg", "t_tray_ware", "t_rlx_isn_yn",
    "goods_pfm_nm", "goods_dtl_pfm_nm", "sound_absorber_yn", "season_nm", "car_knd_nm", "prc_grd_nm",
    "t_oe_maker_1", "oe_badge_yn",
    "wrt_grte_term", "rating_avg",
    # EU 소음 라벨 (정숙성 점수와 별개)
    "label_pnwave", "label_pnwave_nm", "label_pndb",
    # 신규 BE 확장 필드 (사이즈/하중/브랜드/원산지/출시/성능/라벨/공임·보증)
    "big_goods_nm", "ptrn_d_nm",
    "tire_width", "tire_series", "inch", "t_wgt_spd",
    "brand_nm", "certify_brand_nm", "orpl_nm", "t_rls_yearmon",
    "t_high_perform", "t_handling", "t_dryroad_brk", "rr",
    "wage_prc", "wage_today_prc", "free_guarantee_yn",
    # 회원 보유 쿠폰 기반 최저가 (BE 측 enrich, tstation-backend@622ad6a 이후)
    "cheapest_final_prc", "cheapest_total_discount", "cheapest_applied_coupons",
}
_RCMD_QC_FIELDS: set[str] = _RCMD_BASE_FIELDS | {"t_highspd_cd"}
_RCMD_CTX_FIELDS: set[str] = _RCMD_BASE_FIELDS | {"tot_scr", "t_comfort", "t_silence", "t_life_span"}

# Search product base — CTX adds extra_fvr_sale_prc for follow-up price questions.
_SEARCH_PRODUCT_BASE_FIELDS: set[str] = {
    "goods_no", "goods_nm", "tire_size_1",
    # EU 소음 라벨 (정숙성 점수와 별개)
    "label_pnwave", "label_pnwave_nm", "label_pndb",
    # 가격 등급 (프리미엄+/프리미엄/스탠다드/이코노미) — 사용자 등급 질문 답변용
    "prc_grd_nm",
    # 퍼포먼스 분류 (COMFORT=정숙/승차감, SPORT=고속/제동성, RUNFLAT) — 답변용
    "goods_pfm_nm", "goods_dtl_pfm_nm", "sound_absorber_yn",
    "t_oe_maker_1", "oe_badge_yn",
    # 신규 BE 확장 필드
    "big_goods_nm", "ptrn_d_nm",
    "tire_width", "tire_series", "inch",
    "t_wgt_idx", "t_wgt_idx_kg", "t_wgt_spd", "t_highspd",
    "season_nm", "car_knd_nm",
    "brand_nm", "certify_brand_nm", "orpl_nm", "t_rls_yearmon",
    "t_comfort", "t_silence", "t_high_perform", "t_handling",
    "t_life_span", "t_snow", "t_ice", "t_dryroad_brk",
    "rr", "wet",
    "wage_prc", "wage_today_prc", "free_guarantee_yn", "t_rlx_isn_yn",
}
_SEARCH_PRODUCT_CTX_FIELDS: set[str] = _SEARCH_PRODUCT_BASE_FIELDS | {"extra_fvr_sale_prc"}

# ──────────────────────────────────────────────────────────────────────────────

# tool_name → {list_key, keep_fields} for list-type responses
_LIST_TOOL_RULES: dict[str, dict[str, Any]] = {
    "search_stores_tool": {
        "list_key": "stores",
        "keep": _NEARBY_STORE_FIELDS,
    },
    "get_nearby_stores_tool": {
        "list_key": "stores",
        "keep": _NEARBY_STORE_FIELDS,
    },
    "get_store_list_tool": {
        "list_key": "stores",
        "keep": _STORE_BASE_FIELDS,
    },
    "get_favorite_stores_tool": {
        "list_key": "stores",
        "keep": _FAVORITE_STORE_FIELDS,
    },
    "get_products_recommendations_tool": {
        "list_key": "items",
        "keep": _RCMD_QC_FIELDS,
    },
    "search_product_tool": {
        "list_key": "items",
        "keep": _SEARCH_PRODUCT_BASE_FIELDS,
    },
    # sale_qty 는 내부 정렬 근거 — 사용자 노출 금지. QC source 에서 제거해 QC 가 "사실 추가" 정정을 못하도록 차단.
    "get_best_selling_products_tool": {
        "list_key": "items",
        "keep": {
            "goods_no", "goods_nm", "tire_size_1",
            "extra_fvr_sale_prc", "extra_fvr_sale_per",
            # 신규 BE 확장 필드 (베스트셀러도 사용자가 스펙 질문할 수 있음)
            "big_goods_nm", "ptrn_d_nm",
            "tire_width", "tire_series", "inch",
            "t_wgt_idx", "t_wgt_idx_kg", "t_wgt_spd", "t_highspd",
            "season_nm", "car_knd_nm", "goods_pfm_nm",
            "t_oe_maker_1", "oe_badge_yn",
            "brand_nm", "certify_brand_nm", "orpl_nm", "t_rls_yearmon",
            "t_comfort", "t_silence", "t_high_perform", "t_handling",
            "t_life_span", "t_snow", "t_ice", "t_dryroad_brk",
            "rr", "wet", "label_pndb",
            "wage_prc", "wage_today_prc", "free_guarantee_yn", "t_rlx_isn_yn",
        },
    },
    "get_faq_tool": {
        "list_key": "faqs",
        "keep": {"cust_quest", "pc_ans_cont"},
    },
    "get_orders_of_user_tool": {
        "list_key": "orders",
        "keep": _ORDER_FIELDS_BASE,
    },
    "get_my_reservations_tool": {
        "list_key": "reservations",
        "keep": _RESERVATION_FIELDS,
    },
    # 상품별 적용 가능 워런티 — wrt_tp_cd/wrt_nm/is_plus 만 QC 검증/응답 노출용.
    "get_product_warranties_tool": {
        "list_key": "warranties",
        "keep": _PRODUCT_WARRANTY_FIELDS,
    },
    # 회원 보유 워런티 — 가입대기 100 은 BE 에서 이미 필터됨. 한글 라벨 노출.
    "get_my_warranties_tool": {
        "list_key": "warranties",
        "keep": _MY_WARRANTY_FIELDS,
    },
    # 카드사별 무이자 할부 — 응답에는 카드사명/기준금액/가능 개월수만 노출. payment_type
    # 은 trace/QC 식별자로 keep 에 포함하지만 LLM prompt 가 사용자에게 노출하지 않도록 강제.
    "get_card_installments_tool": {
        "list_key": "cards",
        "keep": _CARD_FIELDS,
    },
}

# tool_name → drop_keys for single-object responses
_DROP_TOOL_RULES: dict[str, set[str]] = {
    # slogan / pc_prod_tech_desc / reviews 는 description 요약·리뷰 요약의 출처라 QC 검증에 필요 (drop 금지).
    # pc_prod_remark_desc(보증/AS 템플릿 문구) 와 images 만 QC 검증과 무관해 drop.
    "get_product_description_tool": {"images", "pc_prod_remark_desc"},
}


def _filter_list(items: list[dict], keep: set[str]) -> list[dict]:
    """Keep only whitelisted keys from each item, limit to MAX_LIST_ITEMS."""
    filtered = []
    for item in items[:MAX_LIST_ITEMS]:
        if isinstance(item, dict):
            filtered.append({k: v for k, v in item.items() if k in keep})
        else:
            filtered.append(item)
    total = len(items)
    if total > MAX_LIST_ITEMS:
        filtered.append({"_truncated": f"{total - MAX_LIST_ITEMS} more items omitted"})
    return filtered


def _filter_drop(data: dict, drop_keys: set[str]) -> dict:
    """Remove specified keys from a dict."""
    return {k: v for k, v in data.items() if k not in drop_keys}


# --- Context filter rules (for conversation context preservation) ---
# Keeps more fields than QC filter to maintain conversational references.
_CONTEXT_LIST_RULES: dict[str, dict[str, Any]] = {
    "get_products_recommendations_tool": {
        "list_key": "items",
        "keep": _RCMD_CTX_FIELDS,
    },
    "search_product_tool": {
        "list_key": "items",
        "keep": _SEARCH_PRODUCT_CTX_FIELDS,
    },
    "search_stores_tool": {
        "list_key": "stores",
        "keep": _NEARBY_STORE_FIELDS,
    },
    "get_nearby_stores_tool": {
        "list_key": "stores",
        "keep": _NEARBY_STORE_FIELDS,
    },
    "get_store_list_tool": {
        "list_key": "stores",
        "keep": _STORE_BASE_FIELDS,
    },
    "get_favorite_stores_tool": {
        "list_key": "stores",
        "keep": _FAVORITE_STORE_FIELDS,
    },
    "get_store_inventory_tool": {
        "list_key": "items",
        "keep": {"goods_no", "goods_nm", "tire_size_1", "stock_qty"},
    },
    "get_orders_of_user_tool": {
        "list_key": "orders",
        "keep": _ORDER_FIELDS_BASE | {"ord_stat_nm"},
    },
    "get_my_reservations_tool": {
        "list_key": "reservations",
        "keep": _RESERVATION_FIELDS,
    },
    "check_compatibility_tool": {
        "list_key": "tire_sizes",
        "keep": {"tire_size", "rim_size", "is_oem"},
    },
    # 후속 턴 "방금 본 그 상품 워런티 다시 알려줘" / "내 안심서비스 만료일 다시" 참조용.
    "get_product_warranties_tool": {
        "list_key": "warranties",
        "keep": _PRODUCT_WARRANTY_FIELDS,
    },
    "get_my_warranties_tool": {
        "list_key": "warranties",
        "keep": _MY_WARRANTY_FIELDS,
    },
    # 후속 턴 "방금 본 무이자 카드 다시 알려줘" / "12개월 가능 카드 다시" 참조용.
    "get_card_installments_tool": {
        "list_key": "cards",
        "keep": _CARD_FIELDS,
    },
}

_CONTEXT_MAX_ITEMS = 10

# Whitelist for tool input fields safe to persist into prompt context.
# Excludes PII: car_no, owner_nm, mbr_no, user_id, user_xpos, user_ypos, access_token
_SAFE_INPUT_FIELDS = {
    # product/search
    "tire_size", "goods_no", "keyword", "limit", "size", "brand", "brand_cd",
    "rcmd_type", "entr_yn", "entr_no", "car_lnc_cd",
    # store
    "shop_id", "shop_nm", "store_nm", "region_code",
    "radius_km", "svc_codes", "all_my_t_only", "chl_sct_cd",
    # vehicle (non-PII)
    "car_model", "car_year", "car_grade", "car_engine", "rim_size",
    # order/price
    "ord_no", "member_type", "sort", "category",
    # inventory
    "goods_list", "shop_id_list",
}


def _filter_input(tool_input: dict) -> dict:
    """Keep only safe, non-PII fields from tool input (for prompt display)."""
    return {k: v for k, v in tool_input.items() if v is not None and k in _SAFE_INPUT_FIELDS}


def _dedup_input(tool_input: dict) -> dict:
    """Build dedup-safe input: safe fields as-is, PII fields as stable hashes."""
    import hashlib
    result = {}
    for k, v in tool_input.items():
        if v is None:
            continue
        if k in _SAFE_INPUT_FIELDS:
            result[k] = v
        else:
            # Hash PII values so dedup works without storing raw PII
            result[k] = hashlib.sha256(str(v).encode()).hexdigest()[:12]
    return result


def filter_for_context(tool_name: str, raw_output: str, tool_input: dict | None = None) -> dict | None:
    """Filter tool output for conversation context preservation.

    Returns a compact dict with tool name, input summary, and filtered output.
    Returns None if the tool has no context-relevant data.
    """
    try:
        data = json.loads(raw_output) if isinstance(raw_output, str) else raw_output
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    inner = data.get("data", data)

    # Skip error responses
    if data.get("status") == "error":
        return None

    # Tools with specific list filtering
    if tool_name in _CONTEXT_LIST_RULES:
        rule = _CONTEXT_LIST_RULES[tool_name]
        list_key = rule["list_key"]
        keep = rule["keep"]

        items = None
        if isinstance(inner, dict) and list_key in inner and isinstance(inner[list_key], list):
            items = inner[list_key]
        elif isinstance(inner, dict):
            for k, v in inner.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    items = v
                    break

        if items:
            filtered_items = _filter_list(items, keep)
            result = {"tool": tool_name, "data": filtered_items}
            if tool_input:
                result["input"] = _filter_input(tool_input)
                result["_dedup_input"] = _dedup_input(tool_input)
            return result

    # Single-object store detail, preserved for follow-up CTA/detail summaries.
    if tool_name == "get_store_detail_tool" and isinstance(inner, dict):
        compact = {k: v for k, v in inner.items() if k in _STORE_DETAIL_FIELDS and v is not None}
        if compact:
            result = {"tool": tool_name, "data": compact}
            if tool_input:
                result["input"] = _filter_input(tool_input)
                result["_dedup_input"] = _dedup_input(tool_input)
            return result

    # Store schedule results must survive into follow-up turns so "예약 가능 시간 보여줘"
    # can rebuild a datepick even if the previous turn rendered as a quickReply.
    if tool_name == "get_store_schedule_tool" and isinstance(inner, dict):
        compact = {k: v for k, v in inner.items() if k in _STORE_SCHEDULE_FIELDS and v is not None}
        slots = compact.get("slots")
        if isinstance(slots, list):
            compact["slots"] = _filter_list([slot for slot in slots if isinstance(slot, dict)], keep={"cal_day", "tm"})
        if compact:
            result = {"tool": tool_name, "data": compact}
            if tool_input:
                result["input"] = _filter_input(tool_input)
                result["_dedup_input"] = _dedup_input(tool_input)
            return result

    # Single-object tools (price, product description, etc.)
    if tool_name in ("get_final_price_tool", "get_product_description_tool"):
        if isinstance(inner, dict):
            # Keep key pricing/product fields + 신규 BE 확장 필드 (후속 턴 참조용)
            compact = {}
            keep_keys = (
                "goods_no", "goods_nm", "tire_size_1", "sale_prc", "extra_fvr_sale_prc",
                "rating_avg", "review_count", "slogan",
                # 신규 BE 확장 — description 응답이 가장 풍부하므로 컨텍스트에 핵심만 보존
                "big_goods_nm", "ptrn_d_nm",
                "tire_width", "tire_series", "inch",
                "t_wgt_idx", "t_wgt_idx_kg", "t_wgt_spd", "t_highspd",
                "season_nm", "car_knd_nm", "goods_pfm_nm", "goods_dtl_pfm_nm", "sound_absorber_yn",
                "t_oe_maker_1", "oe_badge_yn",
                "brand_nm", "certify_brand_nm", "orpl_nm", "t_rls_yearmon",
                "rr", "wet", "label_pndb",
                "wage_prc", "wage_today_prc", "free_guarantee_yn", "t_rlx_isn_yn",
            )
            for k in keep_keys:
                if k in inner and inner[k] is not None:
                    compact[k] = inner[k]
            if compact:
                result = {"tool": tool_name, "data": compact}
                if tool_input:
                    result["input"] = _filter_input(tool_input)
                    result["_dedup_input"] = _dedup_input(tool_input)
                return result

    return None


def filter_source_data(tool_name: str, raw_output: str) -> str:
    """Filter tool output JSON, keeping only QC-relevant fields.

    Args:
        tool_name: LangChain tool name (e.g. "get_nearby_stores_tool").
        raw_output: Original JSON string from the tool.

    Returns:
        Compact JSON string with irrelevant fields removed.
    """
    # No rule for this tool → pass through as-is
    if tool_name not in _LIST_TOOL_RULES and tool_name not in _DROP_TOOL_RULES:
        return raw_output

    try:
        data = json.loads(raw_output) if isinstance(raw_output, str) else raw_output
    except (json.JSONDecodeError, TypeError):
        return raw_output

    if not isinstance(data, dict):
        return raw_output

    inner = data.get("data", data)

    # List-type filtering
    if tool_name in _LIST_TOOL_RULES:
        rule = _LIST_TOOL_RULES[tool_name]
        list_key = rule["list_key"]
        keep = rule["keep"]

        if isinstance(inner, dict) and list_key in inner and isinstance(inner[list_key], list):
            inner[list_key] = _filter_list(inner[list_key], keep)
        elif isinstance(inner, dict):
            # Try to find any list in the response
            for k, v in inner.items():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    inner[k] = _filter_list(v, keep)
                    break

    # Drop-key filtering
    if tool_name in _DROP_TOOL_RULES:
        drop_keys = _DROP_TOOL_RULES[tool_name]
        if isinstance(inner, dict):
            filtered_inner = _filter_drop(inner, drop_keys)
            if "data" in data:
                data["data"] = filtered_inner
            else:
                data = filtered_inner

    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
