"""Filter tool outputs to keep only QC-relevant fields before passing to QC Agent.

Reduces token count and prevents Lost-in-the-Middle issues by stripping
fields the QC Agent never needs to verify (images, scores, biz hours, etc.).
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_LIST_ITEMS = 10

# tool_name → {list_key, keep_fields} for list-type responses
_LIST_TOOL_RULES: dict[str, dict[str, Any]] = {
    "get_nearby_stores_tool": {
        "list_key": "stores",
        "keep": {"shop_id", "shop_nm", "distance_km", "addr_base", "addr_dtl", "tel_no", "svc_codes"},
    },
    "get_store_list_tool": {
        "list_key": "stores",
        "keep": {"shop_id", "shop_nm", "addr_base", "addr_dtl", "tel_no", "svc_codes"},
    },
    "get_products_recommendations_tool": {
        "list_key": "items",
        "keep": {
            "goods_no", "goods_nm", "tire_size_1",
            "sale_prc", "extra_fvr_sale_prc", "extra_fvr_sale_per",
            # 신규 케이스용 점수/속성 (QC 사실 검증용)
            "wet", "t_snow", "t_ice", "t_highspd", "t_highspd_cd",
            "t_high_hand_avg", "t_com_sil_avg", "t_com_cvs", "t_milg_cvs",
            "t_wgt_idx", "t_wgt_idx_kg", "t_tray_ware", "t_rlx_isn_yn",
            "goods_pfm_nm", "season_nm", "car_knd_nm", "prc_grd_nm",
            "wrt_grte_term", "rating_avg",
            # EU 소음 라벨 (정숙성 점수와 별개)
            "label_pnwave", "label_pnwave_nm", "label_pndb",
            # 신규 BE 확장 필드 (사이즈/하중/브랜드/원산지/출시/성능/라벨/공임·보증)
            "big_goods_nm", "ptrn_d_nm",
            "tire_width", "tire_series", "inch",
            "t_wgt_spd",
            "brand_nm", "certify_brand_nm", "orpl_nm", "t_rls_yearmon",
            "t_high_perform", "t_handling", "t_dryroad_brk", "rr",
            "wage_prc", "wage_today_prc", "free_guarantee_yn",
        },
    },
    "search_product_tool": {
        "list_key": "items",
        "keep": {
            "goods_no", "goods_nm", "tire_size_1",
            # EU 소음 라벨 (정숙성 점수와 별개)
            "label_pnwave", "label_pnwave_nm", "label_pndb",
            # 가격 등급 (프리미엄+/프리미엄/스탠다드/이코노미) — 사용자 등급 질문 답변용
            "prc_grd_nm",
            # 퍼포먼스 분류 (COMFORT=정숙/승차감, SPORT=고속/제동성, RUNFLAT) — 답변용
            "goods_pfm_nm",
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
        },
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
        "keep": {"ord_no", "goods_no", "goods_nm", "tire_size_1", "tire_size_2", "ord_qty", "sys_reg_dtime"},
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
        "keep": {
            "goods_no", "goods_nm", "tire_size_1",
            "sale_prc", "extra_fvr_sale_prc", "extra_fvr_sale_per",
            "tot_scr", "t_comfort", "t_silence", "t_life_span",
            # 신규 케이스용 점수/속성 (대화 컨텍스트 보존)
            "wet", "t_snow", "t_ice", "t_highspd",
            "t_high_hand_avg", "t_com_sil_avg", "t_com_cvs", "t_milg_cvs",
            "t_wgt_idx", "t_tray_ware", "t_rlx_isn_yn",
            "goods_pfm_nm", "season_nm", "car_knd_nm", "prc_grd_nm",
            "wrt_grte_term", "rating_avg",
            # EU 소음 라벨 (정숙성 점수와 별개)
            "label_pnwave", "label_pnwave_nm", "label_pndb",
            # 신규 BE 확장 필드 (후속 턴 참조용 — "방금 본 그 상품 공임비?")
            "big_goods_nm", "ptrn_d_nm",
            "tire_width", "tire_series", "inch",
            "t_wgt_idx_kg", "t_wgt_spd",
            "brand_nm", "certify_brand_nm", "orpl_nm", "t_rls_yearmon",
            "t_high_perform", "t_handling", "t_dryroad_brk", "rr",
            "wage_prc", "wage_today_prc", "free_guarantee_yn",
        },
    },
    "search_product_tool": {
        "list_key": "items",
        "keep": {
            "goods_no", "goods_nm", "tire_size_1", "extra_fvr_sale_prc",
            # EU 소음 라벨 (정숙성 점수와 별개)
            "label_pnwave", "label_pnwave_nm", "label_pndb",
            # 가격 등급 (프리미엄+/프리미엄/스탠다드/이코노미) — 후속 턴에서 등급 질문 답변용
            "prc_grd_nm",
            # 퍼포먼스 분류 (COMFORT=정숙/승차감, SPORT=고속/제동성, RUNFLAT) — 후속 턴 답변용
            "goods_pfm_nm",
            # 신규 BE 확장 필드 (후속 턴 참조용)
            "big_goods_nm", "ptrn_d_nm",
            "tire_width", "tire_series", "inch",
            "t_wgt_idx", "t_wgt_idx_kg", "t_wgt_spd", "t_highspd",
            "season_nm", "car_knd_nm",
            "brand_nm", "certify_brand_nm", "orpl_nm", "t_rls_yearmon",
            "t_comfort", "t_silence", "t_high_perform", "t_handling",
            "t_life_span", "t_snow", "t_ice", "t_dryroad_brk",
            "rr", "wet",
            "wage_prc", "wage_today_prc", "free_guarantee_yn", "t_rlx_isn_yn",
        },
    },
    "get_nearby_stores_tool": {
        "list_key": "stores",
        "keep": {"shop_id", "shop_nm", "distance_km", "addr_base", "addr_dtl", "tel_no", "svc_codes"},
    },
    "get_store_list_tool": {
        "list_key": "stores",
        "keep": {"shop_id", "shop_nm", "addr_base", "addr_dtl", "tel_no", "svc_codes"},
    },
    "get_store_inventory_tool": {
        "list_key": "items",
        "keep": {"goods_no", "goods_nm", "tire_size_1", "stock_qty"},
    },
    "get_orders_of_user_tool": {
        "list_key": "orders",
        "keep": {"ord_no", "goods_no", "goods_nm", "tire_size_1", "tire_size_2", "ord_qty", "ord_stat_nm", "sys_reg_dtime"},
    },
    "check_compatibility_tool": {
        "list_key": "tire_sizes",
        "keep": {"tire_size", "rim_size", "is_oem"},
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
                "season_nm", "car_knd_nm", "goods_pfm_nm",
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
