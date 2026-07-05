"""Response builders for owned-coupon and coupon applicability flows."""

from __future__ import annotations

import calendar
import datetime
import re
from typing import Any

from services.tstation.common.cta_urls import CTAUrls
from services.tstation.policies.price_response_policy import (
    build_price_intent_frame,
    is_product_coupon_price_amount_query,
)
from services.tstation.policies.resolved_context import canonical_context_from_tool_boundary

_COUPON_ISSUE_INTENT_RE = re.compile(
    r"(?:쿠폰|할인권|쿠폰함).{0,20}"
    r"(?:받(?:아|기|을)|다운(?:로드|받)?(?:\s*(?:돼|되|가능|해|해줘))?|"
    r"발급(?:해|해줘|받|받아|해도|돼|되|가능)?|"
    r"만들(?:어|어줘|어\s*줘|라고|어라|어도)|넣(?:어|어줘|어\s*줘)|어떻게\s*받)|"
    r"(?:받(?:아|기|을)|다운(?:로드|받)?(?:\s*(?:돼|되|가능|해|해줘))?|"
    r"발급(?:해|해줘|받|받아|해도|돼|되|가능)?|"
    r"만들(?:어|어줘|어\s*줘|라고|어라|어도)|넣(?:어|어줘|어\s*줘))"
    r".{0,20}(?:쿠폰|할인권|쿠폰함)"
)

_COUPON_BOX_CHIPS: list[dict] = [
    {"label": "쿠폰함 바로가기", "url": CTAUrls.MY_COUPON_LIST_PC, "domain": "TRANSACTION"},
    {"label": "내 쿠폰 조회", "domain": "TRANSACTION"},
]

_OWNED_COUPON_BEST_DISCOUNT_RE = re.compile(
    r"(?:내|내가\s*가진|가진|보유|보유한).{0,12}쿠폰.{0,30}(?:제일|가장|최대|많이|큰|높은)",
    re.IGNORECASE,
)

_COUPON_DIRECT_ID_RE = re.compile(r"\bC[A-Za-z0-9]{8,}\b")
_COUPON_DISCOUNT_RATE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_COUPON_MATCH_STOPWORDS = {
    "쿠폰",
    "할인쿠폰",
    "할인",
    "할인권",
    "적용",
    "적용가능",
    "가능",
    "상품",
    "대상",
    "어떻게",
    "써",
    "쓸수",
    "쓸수있어",
    "먹어",
    "먹히",
    "사용",
    "있는",
    "쓸수있는",
    "뭐야",
    "뭐",
    "어디",
    "알려줘",
    "확인",
    "혹시",
    "내",
    "제",
    "나의",
    "제가",
    "내가",
    "보유",
    "보유중",
    "가지고",
    "갖고",
    "있는지",
    "있어",
    "있나요",
    "있니",
    "있냐",
    "좀",
    "해줘",
    "가능한",
    "적용받고",
    "싶어",
}
_COUPON_MATCH_TOKEN_SUFFIXES = (
    "에서는",
    "에서",
    "으로",
    "에게",
    "까지",
    "부터",
    "하고",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "도",
    "만",
    "로",
    "에",
    "랑",
    "와",
    "과",
)

def _brand_label_for_code(brand_cd: str) -> str:
    return {
        "HK": "한국타이어",
        "LF": "라우펜",
        "MC": "미쉐린",
        "PI": "피렐리",
        "BS": "브리지스톤",
        "CT": "콘티넨탈",
        "GY": "굿이어",
    }.get(str(brand_cd or "").strip().upper(), "해당 브랜드")



def _unwrap_tool_data(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict):
        nested = data.get("data")
        return nested if isinstance(nested, dict) else data
    return payload

def _to_float(value: Any) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if not text or not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        return None
    return float(text)

def _to_int_or_zero(value: Any) -> int:
    number = _to_float(value)
    return int(number) if number is not None else 0

def _date_from_parts(year: int, month: int, day: int) -> datetime.date | None:
    if month < 1 or month > 12 or day < 1:
        return None
    last_day = calendar.monthrange(year, month)[1]
    if day > last_day:
        return None
    return datetime.date(year, month, day)



def _normalize_coupon_match_text(value: object) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(value or "")).lower()


def _strip_coupon_match_token_suffix(token: str) -> str:
    for suffix in _COUPON_MATCH_TOKEN_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            return token[: -len(suffix)]
    return token


_PRODUCT_MATCH_ALIAS_GROUPS = (
    {"kinergyex", "키너지ex"},
    {"dynaprohpx", "다이나프로hpx"},
    {"dynaprohp3", "다이나프로hp3"},
    {"ventusairs", "벤투스airs", "벤투스에어s"},
    {"ventuss2", "벤투스s2"},
    {"ventuss2as", "벤투스s2as"},
    {"ventuss1evozas", "벤투스s1evozas", "벤투스s1에보zas"},
    {"ventuss1evoz", "벤투스s1evoz", "벤투스s1에보z"},
    {"sfitas", "에스핏as"},
    {"sfit", "에스핏"},
    {"ionevoassuv", "아이온에보assuv"},
    {"ionevoas", "아이온에보as"},
    {"ionevo", "아이온에보"},
    {"mileageplus3", "마일리지플러스3"},
    {"mileageplus2", "마일리지플러스2"},
    {"mileageplus", "마일리지플러스"},
)


def _coupon_product_match_keys(value: object) -> set[str]:
    normalized = _normalize_coupon_match_text(value)
    if not normalized:
        return set()
    keys = {normalized}
    for group in _PRODUCT_MATCH_ALIAS_GROUPS:
        if normalized in group:
            keys.update(group)
            break
    return keys


def _product_name_match_tokens(value: object) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r"[0-9A-Za-z가-힣]+", str(value or "")):
        token = _normalize_coupon_match_text(raw)
        if len(token) < 2:
            continue
        tokens.add(token)
    return tokens


def _is_strong_product_name_match(target_name: object, row_name: object) -> bool:
    target_norm = _normalize_coupon_match_text(target_name)
    row_norm = _normalize_coupon_match_text(row_name)
    if not target_norm or not row_norm:
        return False

    if _coupon_product_match_keys(target_name) & _coupon_product_match_keys(row_name):
        return True

    if min(len(target_norm), len(row_norm)) >= 5 and (target_norm in row_norm or row_norm in target_norm):
        return True

    target_tokens = _product_name_match_tokens(target_name)
    row_tokens = _product_name_match_tokens(row_name)
    return len(target_tokens & row_tokens) >= 2


def _coupon_query_terms(user_text: str) -> list[str]:
    terms: list[str] = []
    for raw in re.findall(r"[0-9a-zA-Z가-힣]+", user_text):
        normalized = _normalize_coupon_match_text(raw)
        normalized = _strip_coupon_match_token_suffix(normalized)
        if len(normalized) < 2 or normalized in _COUPON_MATCH_STOPWORDS:
            continue
        terms.append(normalized)
    return terms


def normalize_coupon_match_text(value: object) -> str:
    return _normalize_coupon_match_text(value)

def coupon_product_match_keys(value: object) -> set[str]:
    return _coupon_product_match_keys(value)

def product_name_match_tokens(value: object) -> set[str]:
    return _product_name_match_tokens(value)

def strong_product_name_match(target_name: object, row_name: object) -> bool:
    return _is_strong_product_name_match(target_name, row_name)

def coupon_query_terms(user_text: str) -> list[str]:
    return _coupon_query_terms(user_text)

def _coupon_rows_from_my_coupons(tool_result: dict) -> list[dict]:
    data = _unwrap_tool_data(tool_result)
    rows = data.get("coupons")
    if rows is None:
        rows = data.get("items")
    return [row for row in rows or [] if isinstance(row, dict)]


def _chunk_coupon_numbers(cpn_nos: list[str], *, batch_size: int = 10) -> list[list[str]]:
    normalized = [str(cpn_no).strip() for cpn_no in cpn_nos if str(cpn_no).strip()]
    if batch_size <= 0:
        return [normalized] if normalized else []
    return [normalized[index : index + batch_size] for index in range(0, len(normalized), batch_size)]


def _merge_coupon_applicable_products_results(results: list[dict]) -> dict:
    merged_coupons: list[dict] = []
    merged_deals: list[dict] = []
    merged_stores: list[dict] = []
    for result in results:
        data = _unwrap_tool_data(result)
        merged_coupons.extend(
            item for item in data.get("coupons", []) if isinstance(item, dict)
        )
        merged_deals.extend(
            item for item in data.get("deals", []) if isinstance(item, dict)
        )
        merged_stores.extend(
            item for item in data.get("stores", []) if isinstance(item, dict)
        )

    return {
        "status": "success",
        "http_status": 200,
        "data": {
            "total_coupons": len(merged_coupons),
            "total_deals": len(merged_deals),
            "total_products": (
                sum(int(group.get("total") or 0) for group in merged_coupons)
                + sum(int(group.get("total") or 0) for group in merged_deals)
            ),
            "total_store_coupons": len(merged_stores),
            "total_stores": sum(int(group.get("total") or 0) for group in merged_stores),
            "coupons": merged_coupons,
            "deals": merged_deals,
            "stores": merged_stores,
        },
    }


_OWNED_COUPON_EXPIRY_LOOKUP_RE = re.compile(
    r"(?=.*(?:쿠폰|할인권))(?=.*(?:내|나의|보유|가진|갖고|받은|쿠폰함))"
    r"(?=.*(?:이번\s*달|이달|곧|만료\s*예정|만료(?:되는|인|된)?|유효\s*기간|사용\s*기간))",
    re.IGNORECASE,
)
_COUPON_RESTORE_INTENT_RE = re.compile(
    r"원복|복구|재사용|다시\s*(?:쓰|쓸|사용)|되살|살려|부활|연장|못\s*쓰.*(?:해줘|할\s*수)",
    re.IGNORECASE,
)


def _is_owned_coupon_expiry_lookup_query(user_text: str) -> bool:
    text = user_text or ""
    if _COUPON_RESTORE_INTENT_RE.search(text):
        return False
    return bool(_OWNED_COUPON_EXPIRY_LOOKUP_RE.search(text))


def _owned_coupon_expiry_scope(user_text: str) -> str:
    text = user_text or ""
    if re.search(r"이번\s*달|이달", text):
        return "this_month"
    if re.search(r"이미|지난|만료\s*된", text):
        return "expired"
    if re.search(r"곧|만료\s*예정", text):
        return "soon"
    return "expiring"


def _coupon_end_date(row: dict) -> datetime.date | None:
    raw = str(
        row.get("use_end_dtime")
        or row.get("use_end_date")
        or row.get("end_dtime")
        or row.get("end_date")
        or row.get("valid_end_date")
        or ""
    ).strip()
    if not raw:
        return None
    compact = re.search(r"(20\d{2})(\d{2})(\d{2})", raw)
    if compact:
        year, month, day = (int(part) for part in compact.groups())
    else:
        match = re.search(r"(20\d{2})\D+(\d{1,2})\D+(\d{1,2})", raw)
        if not match:
            return None
        year, month, day = (int(part) for part in match.groups())
    return _date_from_parts(year, month, day)


def _coupon_expiry_matches_scope(end_date: datetime.date, scope: str, today: datetime.date) -> bool:
    if scope == "this_month":
        return end_date >= today and end_date.year == today.year and end_date.month == today.month
    if scope == "soon":
        return today <= end_date <= today + datetime.timedelta(days=30)
    if scope == "expired":
        return end_date < today
    return end_date >= today


def _format_coupon_discount_text(row: dict) -> str:
    value = _coupon_numeric_value(row)
    if value is None:
        return ""
    if _looks_like_percent_coupon(row):
        return f"{value:g}% 할인"
    return f"{int(value):,}원 할인"


def _build_owned_coupon_expiry_lookup_event(user_text: str, tool_result: dict) -> dict:
    rows = _coupon_rows_from_my_coupons(tool_result)
    today = datetime.date.today()
    scope = _owned_coupon_expiry_scope(user_text)
    matched: list[tuple[datetime.date, dict]] = []
    for row in rows:
        end_date = _coupon_end_date(row)
        if end_date and _coupon_expiry_matches_scope(end_date, scope, today):
            matched.append((end_date, row))
    matched.sort(key=lambda item: item[0])

    scope_label = {
        "this_month": "이번 달 안에 만료되는",
        "soon": "곧 만료되는",
        "expired": "이미 만료된",
        "expiring": "만료 예정인",
    }[scope]
    if matched:
        lines = [f"보유 쿠폰 중 {scope_label} 쿠폰은 {len(matched)}개예요."]
        for end_date, row in matched[:10]:
            name = str(row.get("cpn_nm") or row.get("disp_nm") or row.get("cpn_d_nm") or "쿠폰").strip()
            discount = _format_coupon_discount_text(row)
            suffix = f" - {discount}" if discount else ""
            lines.append(f"- {name}{suffix} / 만료일 {end_date.isoformat()}")
        if len(matched) > 10:
            lines.append(f"외 {len(matched) - 10}개는 쿠폰함에서 확인해 주세요.")
        assistant_response = "\n".join(lines)
    else:
        assistant_response = f"현재 보유 쿠폰 중 {scope_label} 쿠폰은 없어요."

    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_owned_coupon_expiry_lookup",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": [
                {"label": "내 쿠폰함", "url": CTAUrls.MY_COUPON_LIST_PC, "domain": "TRANSACTION"},
                {"label": "구매하기", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["TRANSACTION"],
        },
    }


def _is_owned_coupon_best_discount_query(user_text: str) -> bool:
    if _COUPON_ISSUE_INTENT_RE.search(user_text or ""):
        return False
    if _is_product_coupon_eligibility_query(user_text or ""):
        return False
    return bool(_OWNED_COUPON_BEST_DISCOUNT_RE.search(user_text or ""))


def _is_specific_owned_coupon_lookup_query(user_text: str) -> bool:
    hint = _specific_owned_coupon_lookup_hint(user_text)
    return bool(hint)


def _specific_owned_coupon_lookup_hint(user_text: str) -> str | None:
    text = user_text or ""
    if not re.search(r"쿠폰|할인권", text, re.IGNORECASE):
        return None
    if _COUPON_ISSUE_INTENT_RE.search(text):
        return None
    if (
        _is_strong_coupon_applicability_query(text)
        or _is_product_coupon_eligibility_query(text)
        or _is_owned_coupon_best_discount_query(text)
    ):
        return None
    if re.search(r"적용|사용|쓸\s*수|살\s*수|상품|가장\s*싸|제일\s*싸|최대\s*혜택|혜택", text):
        return None
    if not re.search(r"있|보유|가지|갖|확인", text):
        return None

    raw_terms = re.findall(r"[0-9a-zA-Z가-힣]+", text)
    terms: list[str] = []
    extra_stopwords = {
        "쿠폰",
        "할인쿠폰",
        "할인권",
        "혹시",
        "내",
        "제",
        "나의",
        "제가",
        "내가",
        "나",
        "보유",
        "보유중",
        "가지고",
        "갖고",
        "있는지",
        "있어",
        "있나요",
        "있니",
        "있냐",
        "있을까",
        "확인",
        "좀",
        "알려줘",
    }
    for raw in raw_terms:
        normalized = _normalize_coupon_match_text(raw)
        for suffix in (
            "보유중이야",
            "보유중인가",
            "보유중인지",
            "보유중",
            "보유한가",
            "보유인지",
            "있나요",
            "있는지",
            "있을까",
            "있어",
            "있니",
            "있냐",
            "확인해줘",
            "확인",
        ):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
        if not normalized or normalized in extra_stopwords:
            continue
        for suffix in ("할인쿠폰", "쿠폰", "할인권"):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
        if len(normalized) >= 2 and normalized not in extra_stopwords:
            terms.append(normalized)
    if not terms:
        return None
    return " ".join(terms[:3])


def _owned_coupon_lookup_summary_text(user_text: str, tool_result: dict) -> str | None:
    hint = _specific_owned_coupon_lookup_hint(user_text)
    if not hint:
        return None
    matched_coupon = _find_coupon_from_owned_coupons(f"{hint} 쿠폰", tool_result)
    if matched_coupon:
        coupon_name = str(
            matched_coupon.get("cpn_nm") or matched_coupon.get("disp_nm") or matched_coupon.get("cpn_d_nm") or hint
        ).strip()
        return f"‘{coupon_name}’ 관련 쿠폰을 보유 중이에요.\n아래에서 현재 보유 쿠폰 목록도 함께 확인해 주세요."
    return f"현재 보유 쿠폰에서 ‘{hint}’ 관련 쿠폰은 확인되지 않아요.\n아래에서 현재 보유 쿠폰 목록을 확인해 주세요."


def _coupon_numeric_value(row: dict) -> float | None:
    value = _to_float(row.get("rt_amt_val"))
    return value if value > 0 else None


def _looks_like_percent_coupon(row: dict) -> bool:
    value = _coupon_numeric_value(row)
    if value is None or value > 100:
        return False
    coupon_name = str(row.get("cpn_nm") or row.get("disp_nm") or row.get("cpn_d_nm") or "")
    return "%" in coupon_name or "퍼센트" in coupon_name or "할인율" in coupon_name


def _format_coupon_limit_text(row: dict) -> str:
    parts: list[str] = []
    min_purchase = _to_int_or_zero(row.get("min_pur_amt"))
    max_discount = _to_int_or_zero(row.get("max_dscnt_amt"))
    if min_purchase > 0:
        parts.append(f"최소 구매금액 {min_purchase:,}원")
    if max_discount > 0:
        parts.append(f"최대 할인 {max_discount:,}원")
    end_time = str(row.get("use_end_dtime") or "").strip()
    if end_time:
        parts.append(f"유효기간 {end_time}")
    return ", ".join(parts)


def _build_owned_coupon_best_discount_event(tool_result: dict) -> dict:
    rows = [row for row in _coupon_rows_from_my_coupons(tool_result) if str(row.get("mbr_use_yn") or "N") != "Y"]
    percent_rows = [row for row in rows if _looks_like_percent_coupon(row)]
    amount_rows = [row for row in rows if (_coupon_numeric_value(row) or 0) > 100]
    best_percent = max(percent_rows, key=lambda row: _coupon_numeric_value(row) or 0, default=None)
    best_amount = max(amount_rows, key=lambda row: _coupon_numeric_value(row) or 0, default=None)

    lines: list[str] = []
    if best_percent:
        name = str(best_percent.get("cpn_nm") or best_percent.get("disp_nm") or "해당 쿠폰")
        value = _coupon_numeric_value(best_percent) or 0
        lines.append(f"보유 쿠폰 중 할인율 기준으로는 ‘{name}’이 가장 커요. ({value:g}% 할인)")
        limit_text = _format_coupon_limit_text(best_percent)
        if limit_text:
            lines.append(f"- 조건: {limit_text}")
    if best_amount:
        name = str(best_amount.get("cpn_nm") or best_amount.get("disp_nm") or "해당 쿠폰")
        value = int(_coupon_numeric_value(best_amount) or 0)
        lines.append(f"정액 할인 기준으로는 ‘{name}’이 가장 커요. ({value:,}원 할인)")
        limit_text = _format_coupon_limit_text(best_amount)
        if limit_text:
            lines.append(f"- 조건: {limit_text}")
    if not lines:
        lines.append("현재 보유 쿠폰에서 할인 금액이나 할인율 정보를 확인하지 못했어요.")
    lines.append("실제 최종 할인액은 상품 가격, 적용 대상, 중복 가능 여부에 따라 달라질 수 있어요.")

    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_owned_coupon_best_discount",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": [
                {"label": "내 쿠폰 조회", "domain": "TRANSACTION"},
                {"label": "상품별 쿠폰 확인", "domain": "TRANSACTION"},
            ],
            "predictedDomains": ["TRANSACTION"],
        },
    }


def _find_coupon_from_owned_coupons(user_text: str, tool_result: dict) -> dict | None:
    rows = _coupon_rows_from_my_coupons(tool_result)
    if not rows:
        return None

    direct_ids = {item.upper() for item in _COUPON_DIRECT_ID_RE.findall(user_text)}
    if direct_ids:
        for row in rows:
            cpn_no = str(row.get("cpn_no") or "").upper()
            if cpn_no in direct_ids:
                return row

    query_norm = _normalize_coupon_match_text(user_text)
    terms = _coupon_query_terms(user_text)
    discount_match = _COUPON_DISCOUNT_RATE_RE.search(user_text)
    requested_rate = float(discount_match.group(1)) if discount_match else None

    best_row: dict | None = None
    best_score = 0.0
    for row in rows:
        coupon_name = str(row.get("cpn_nm") or row.get("disp_nm") or row.get("cpn_d_nm") or "")
        name_norm = _normalize_coupon_match_text(coupon_name)
        if not name_norm:
            continue

        score = 0.0
        if name_norm and name_norm in query_norm:
            score += 100.0
        meaningful_query = "".join(terms)
        if meaningful_query and meaningful_query in name_norm:
            score += 80.0

        matched_terms = [term for term in terms if term in name_norm]
        score += len(matched_terms) * 10.0
        if terms and len(matched_terms) == len(terms):
            score += 20.0

        if requested_rate is not None:
            coupon_rate = _to_float(row.get("rt_amt_val"))
            if coupon_rate is not None and abs(coupon_rate - requested_rate) < 0.001:
                score += 25.0

        if score > best_score:
            best_score = score
            best_row = row

    if best_score >= 20.0:
        return best_row
    if re.search(r"쿠폰|할인권|혜택", user_text or "", re.IGNORECASE) and best_score >= 10.0:
        return best_row
    return None


def _coupon_match_candidates_from_owned_coupons(user_text: str, tool_result: dict) -> list[tuple[dict, float]]:
    rows = _coupon_rows_from_my_coupons(tool_result)
    if not rows:
        return []

    direct_ids = {item.upper() for item in _COUPON_DIRECT_ID_RE.findall(user_text)}
    if direct_ids:
        return [
            (row, 200.0)
            for row in rows
            if str(row.get("cpn_no") or "").upper() in direct_ids
        ]

    query_norm = _normalize_coupon_match_text(user_text)
    terms = _coupon_query_terms(user_text)
    meaningful_query = "".join(terms)
    discount_match = _COUPON_DISCOUNT_RATE_RE.search(user_text)
    requested_rate = float(discount_match.group(1)) if discount_match else None

    scored: list[tuple[dict, float]] = []
    for row in rows:
        coupon_name = str(row.get("cpn_nm") or row.get("disp_nm") or row.get("cpn_d_nm") or "")
        name_norm = _normalize_coupon_match_text(coupon_name)
        if not name_norm:
            continue

        score = 0.0
        if name_norm and name_norm in query_norm:
            score += 100.0
        if meaningful_query and meaningful_query in name_norm:
            score += 80.0

        matched_terms = [term for term in terms if term in name_norm]
        score += len(matched_terms) * 10.0
        if terms and len(matched_terms) == len(terms):
            score += 20.0

        if requested_rate is not None:
            coupon_rate = _to_float(row.get("rt_amt_val"))
            if coupon_rate is not None and abs(coupon_rate - requested_rate) < 0.001:
                score += 25.0

        if score >= 10.0:
            scored.append((row, score))

    return sorted(scored, key=lambda item: item[1], reverse=True)


def _find_single_confident_coupon_from_owned_coupons(user_text: str, tool_result: dict) -> tuple[dict | None, list[dict]]:
    candidates = _coupon_match_candidates_from_owned_coupons(user_text, tool_result)
    if not candidates:
        return None, []

    terms = _coupon_query_terms(user_text)
    if terms:
        term_complete_matches: list[dict] = []
        for row, _score in candidates:
            coupon_name = str(row.get("cpn_nm") or row.get("disp_nm") or row.get("cpn_d_nm") or "")
            name_norm = _normalize_coupon_match_text(coupon_name)
            if name_norm and all(term in name_norm for term in terms):
                term_complete_matches.append(row)
        if len(term_complete_matches) > 1:
            return None, term_complete_matches[:3]

    top_name_norm = _normalize_coupon_match_text(_coupon_name(candidates[0][0], ""))
    prefix_like_matches = [
        row
        for row, score in candidates
        if score >= 10.0
        and top_name_norm
        and (
            top_name_norm in _normalize_coupon_match_text(_coupon_name(row, ""))
            or _normalize_coupon_match_text(_coupon_name(row, "")) in top_name_norm
        )
    ]
    if len(prefix_like_matches) > 1:
        return None, prefix_like_matches[:3]

    if len(candidates) == 1 and candidates[0][1] >= 10.0:
        return candidates[0][0], []

    top_score = candidates[0][1]
    high_confidence = [row for row, score in candidates if score >= max(20.0, top_score - 5.0)]
    if len(high_confidence) == 1 and top_score >= 20.0:
        return high_confidence[0], []
    return None, high_confidence[:3]


def _coupon_name(row: dict, fallback: str = "해당 쿠폰") -> str:
    return str(row.get("cpn_nm") or row.get("disp_nm") or row.get("cpn_d_nm") or fallback).strip() or fallback


def _coupon_mapping_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "t", "y", "yes", "o"}


def _coupon_channel_type(row: dict) -> str:
    channel_type = str(row.get("coupon_channel_type") or "").strip().lower()
    if channel_type:
        return channel_type

    if _coupon_mapping_flag(row.get("has_partner_mapping")):
        return "partner_only"

    cpn_onoff_cd = str(row.get("cpn_onoff_cd") or "").strip()
    if cpn_onoff_cd == "10":
        return "online"
    if cpn_onoff_cd == "20":
        return "onoff"
    if cpn_onoff_cd == "30":
        if _coupon_mapping_flag(row.get("has_store_mapping")):
            return "store_only"
        return "offline"
    return ""


def _coupon_store_names_from_applicable_result(tool_result: dict | None, *, limit: int = 3) -> list[str]:
    data = _unwrap_tool_data(tool_result or {})
    if not isinstance(data, dict):
        return []
    names: list[str] = []
    for group in data.get("stores") or []:
        if not isinstance(group, dict):
            continue
        items = group.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("shop_nm") or item.get("shop_name") or "").strip()
            if name and name not in names:
                names.append(name)
            if len(names) >= limit:
                return names
    return names


def _build_coupon_match_failure_event(user_text: str, candidate_rows: list[dict] | None = None) -> dict:
    candidate_rows = candidate_rows or []
    if candidate_rows:
        names = [_coupon_name(row) for row in candidate_rows[:3]]
        assistant_response = (
            "보유 쿠폰에서 비슷한 쿠폰명이 여러 개 확인돼요. 정확한 쿠폰을 선택해 주세요.\n"
            + "\n".join(f"- {name}" for name in names)
        )
        quick_replies = [{"label": name[:18], "domain": "TRANSACTION"} for name in names[:3]]
        quick_replies.append({"label": "내 쿠폰 조회", "domain": "TRANSACTION"})
    else:
        hint = _specific_owned_coupon_lookup_hint(user_text)
        target = f"‘{hint}’ " if hint else ""
        assistant_response = f"보유 쿠폰에서 {target}정확한 쿠폰명을 찾지 못했어요. 쿠폰함에서 쿠폰명을 확인해 주세요."
        quick_replies = [dict(chip) for chip in _COUPON_BOX_CHIPS]

    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_coupon_match_guard",
        "data": {
            "assistantResponse": assistant_response,
            "quickReplies": quick_replies,
            "predictedDomains": ["TRANSACTION"],
        },
    }


def _build_coupon_channel_policy_event(
    coupon_row: dict,
    *,
    applicable_result: dict | None = None,
    target_product_name: str | None = None,
) -> dict | None:
    channel_type = _coupon_channel_type(coupon_row)
    if channel_type not in {"online", "onoff", "store_only", "offline", "partner_only"}:
        return None

    coupon_name = _coupon_name(coupon_row)
    lines: list[str] = []
    quick_replies: list[dict]
    predicted_domains = ["TRANSACTION"]

    if channel_type == "online":
        lines.append(f"‘{coupon_name}’은 온라인에서 사용 가능한 쿠폰이에요.")
        if target_product_name:
            lines.append("상품/브랜드/패턴 제한은 이어서 적용 대상 기준으로 확인할게요.")
        quick_replies = [
            {"label": "상품 가격 확인", "domain": "TRANSACTION"},
            {"label": "내 쿠폰 조회", "domain": "TRANSACTION"},
        ]
    elif channel_type == "onoff":
        lines.append(f"‘{coupon_name}’은 온라인/오프라인 모두 사용 가능한 쿠폰이에요.")
        lines.append("다만 상품, 브랜드, 패턴 제한은 쿠폰 적용 조건을 별도로 확인해야 해요.")
        quick_replies = [
            {"label": "상품 가격 확인", "domain": "TRANSACTION"},
            {"label": "내 쿠폰 조회", "domain": "TRANSACTION"},
        ]
    elif channel_type == "store_only":
        lines.append(f"‘{coupon_name}’은 매장 전용 쿠폰입니다.")
        lines.append("지정 매장에서 사용할 수 있고, 온라인 상품 가격에는 반영되지 않습니다.")
        store_names = _coupon_store_names_from_applicable_result(applicable_result)
        if store_names:
            lines.append(f"적용 가능 매장은 {', '.join(store_names)}입니다.")
        else:
            lines.append("적용 가능 매장은 쿠폰 적용 매장 조회에서 확인해 주세요.")
        quick_replies = [
            {"label": "적용 매장 보기", "domain": "TRANSACTION"},
            {"label": "내 쿠폰 조회", "domain": "TRANSACTION"},
            {"label": "매장 찾기", "domain": "TRANSACTION"},
        ]
    elif channel_type == "offline":
        lines.append(f"‘{coupon_name}’은 오프라인 전용 쿠폰이에요.")
        lines.append("온라인 상품 가격에는 반영되지 않습니다. 매장 사용 조건은 쿠폰함 또는 매장에서 확인해 주세요.")
        quick_replies = [
            {"label": "내 쿠폰 조회", "domain": "TRANSACTION"},
            {"label": "매장 찾기", "domain": "TRANSACTION"},
        ]
    else:
        lines.append(f"‘{coupon_name}’은 제휴 조건이 필요한 쿠폰이에요.")
        lines.append("일반 회원은 사용이 제한될 수 있어 제휴 조건을 먼저 확인해야 합니다.")
        quick_replies = [
            {"label": "내 쿠폰 조회", "domain": "TRANSACTION"},
            {"label": "1:1 문의하기", "domain": "SUPPORT"},
        ]
        predicted_domains = ["TRANSACTION", "SUPPORT"]

    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_coupon_channel_policy",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": quick_replies,
            "predictedDomains": predicted_domains,
        },
    }



def _build_coupon_applicability_event(
    tool_result: dict,
    coupon_row: dict,
    *,
    target_product_name: str | None = None,
    target_brand: dict | None = None,
) -> dict:
    data = _unwrap_tool_data(tool_result)
    coupon_name = str(coupon_row.get("cpn_nm") or "해당 쿠폰")
    products: list[dict] = []
    stores: list[dict] = []

    for group in data.get("coupons") or []:
        if isinstance(group, dict) and isinstance(group.get("items"), list):
            products.extend(item for item in group["items"] if isinstance(item, dict))
    for group in data.get("stores") or []:
        if isinstance(group, dict) and isinstance(group.get("items"), list):
            stores.extend(item for item in group["items"] if isinstance(item, dict))

    total_products = int(data.get("total_products") or len(products))
    total_stores = int(data.get("total_stores") or len(stores))

    lines: list[str] = []
    if target_brand:
        target_brand_cd = str(target_brand.get("brand_cd") or "").strip().upper()
        target_brand_label = str(target_brand.get("label") or _brand_label_for_code(target_brand_cd)).strip()
        matched_products: list[str] = []
        for item in products:
            row_brand_cd = str(item.get("brand_cd") or item.get("brandCode") or "").strip().upper()
            row_brand_nm = str(item.get("brand_nm") or item.get("brand_name") or item.get("brandName") or "").strip()
            row_goods_nm = str(canonical_context_from_tool_boundary(item).get("product_name") or "").strip()
            if not row_goods_nm:
                continue
            if (
                (target_brand_cd and row_brand_cd == target_brand_cd)
                or (target_brand_label and target_brand_label.casefold() in row_brand_nm.casefold())
                or (target_brand_label and target_brand_label.casefold() in row_goods_nm.casefold())
            ):
                matched_products.append(row_goods_nm)
        if matched_products:
            lines.append(f"‘{coupon_name}’은 {target_brand_label} 상품에도 적용 가능해요.")
            lines.append("확인된 대표 상품은 " + ", ".join(matched_products[:5]) + "입니다.")
        else:
            lines.append(f"적용 가능 상품 목록에서 {target_brand_label} 상품은 확인되지 않았어요.")
            lines.append("쿠폰함에서 상세 적용 조건을 확인해 주세요.")
        quick_replies = [
            {"label": "쿠폰함 바로가기", "url": CTAUrls.MY_COUPON_LIST_PC, "domain": "TRANSACTION"},
            {"label": "내 쿠폰 조회", "domain": "TRANSACTION"},
            {"label": "적용 상품 다시 확인", "domain": "TRANSACTION"},
        ]
        return {
            "type": "data",
            "template": "quickReply",
            "source_domain": "transaction",
            "assistant_response_source": "code_coupon_resolver",
            "data": {
                "assistantResponse": "\n".join(lines),
                "quickReplies": quick_replies,
                "predictedDomains": ["TRANSACTION"],
            },
        }

    target_keys = _coupon_product_match_keys(target_product_name)
    if target_keys:
        product_names = [
            str(canonical_context_from_tool_boundary(item).get("product_name") or "").strip()
            for item in products
            if str(canonical_context_from_tool_boundary(item).get("product_name") or "").strip()
        ]
        matched_product_names = [
            name for name in product_names
            if bool(target_keys & _coupon_product_match_keys(name))
        ]
        target_display_name = matched_product_names[0] if matched_product_names else str(target_product_name or "해당 상품")
        if matched_product_names:
            lines.append(
                f"보유 쿠폰에서 ‘{coupon_name}’을 확인했고, 이 쿠폰은 {target_display_name} 패턴에 적용 가능해요."
            )
            lines.append(
                f"{target_display_name}를 주문하시겠어요? 주문하시려면 타이어 사이즈를 입력하거나 "
                "보유차량 중에서 선택해 맞는 모델을 찾을게요."
            )
        elif products:
            lines.append(
                f"보유 쿠폰에서 ‘{coupon_name}’을 확인했지만, 적용 가능 상품 목록에서 {target_display_name} 패턴은 확인되지 않았어요."
            )
            lines.append("쿠폰함의 적용 조건을 다시 확인해 주세요.")
    elif products:
        lines.append(f"‘{coupon_name}’ 적용 가능 상품은 {total_products}개예요.")
        for item in products[:5]:
            goods_nm = str(canonical_context_from_tool_boundary(item).get("product_name") or "").strip()
            if goods_nm:
                lines.append(f"- {goods_nm}")
        if total_products > 5:
            lines.append(f"외 {total_products - 5}개 상품이 더 있어요.")
    if stores:
        store_names = [
            str(item.get("shop_nm") or "").strip()
            for item in stores[:5]
            if str(item.get("shop_nm") or "").strip()
        ]
        if store_names:
            lines.append(f"사용 가능 매장은 {', '.join(store_names)}예요.")
            if total_stores > 5:
                lines.append(f"외 {total_stores - 5}개 매장이 더 있어요.")

    quick_replies = [
        {"label": "보유차량 중 선택", "domain": "DISCOVERY"},
        {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
        {"label": "내 쿠폰 조회", "domain": "TRANSACTION"},
    ]
    predicted_domains = ["DISCOVERY", "TRANSACTION"]
    if not lines:
        lines.append("해당 쿠폰의 적용 정보를 찾을 수 없어요. 쿠폰함에서 적용 대상을 확인해 주세요.")
        quick_replies = [dict(chip) for chip in _COUPON_BOX_CHIPS]
        predicted_domains = ["TRANSACTION"]

    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_coupon_resolver",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": quick_replies,
            "predictedDomains": predicted_domains,
        },
    }


def _build_product_coupon_eligibility_event(
    tool_result: dict,
    coupon_rows: list[dict],
    *,
    target_product_name: str,
    target_brand: dict | None = None,
) -> dict:
    data = _unwrap_tool_data(tool_result)
    target_display_name = str(target_product_name or "해당 상품").strip() or "해당 상품"
    if target_brand:
        target_brand_cd = str(target_brand.get("brand_cd") or "").strip().upper()
        target_brand_label = str(target_brand.get("label") or _brand_label_for_code(target_brand_cd)).strip()
        target_display_name = target_brand_label or target_display_name
        target_keys = set()
    else:
        target_keys = _coupon_product_match_keys(target_display_name)
    coupon_name_by_no = {
        str(row.get("cpn_no") or "").strip(): str(row.get("cpn_nm") or row.get("disp_nm") or "해당 쿠폰").strip()
        for row in coupon_rows
        if str(row.get("cpn_no") or "").strip()
    }
    applicable_coupon_names: list[str] = []
    matched_product_name = ""

    for group in data.get("coupons") or []:
        if not isinstance(group, dict):
            continue
        cpn_no = str(group.get("cpn_no") or "").strip()
        coupon_name = coupon_name_by_no.get(cpn_no) or cpn_no or "해당 쿠폰"
        items = group.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            goods_nm = str(canonical_context_from_tool_boundary(item).get("product_name") or "").strip()
            if not goods_nm:
                continue
            if target_brand:
                row_brand_cd = str(item.get("brand_cd") or item.get("brandCode") or "").strip().upper()
                row_brand_nm = str(item.get("brand_nm") or item.get("brand_name") or item.get("brandName") or "").strip()
                matched_target = (
                    (target_brand_cd and row_brand_cd == target_brand_cd)
                    or (target_brand_label and target_brand_label.casefold() in row_brand_nm.casefold())
                    or (target_brand_label and target_brand_label.casefold() in goods_nm.casefold())
                )
            else:
                matched_target = bool(
                    target_keys and (
                        target_keys & _coupon_product_match_keys(goods_nm)
                        or any(
                            target and row_term and (target in row_term or row_term in target)
                            for target in target_keys
                            for row_term in _coupon_product_match_keys(goods_nm)
                        )
                    )
                )
            if matched_target:
                if coupon_name not in applicable_coupon_names:
                    applicable_coupon_names.append(coupon_name)
                matched_product_name = matched_product_name or goods_nm
                break

    if applicable_coupon_names:
        if target_brand:
            lines = [
                f"보유 쿠폰 기준으로 {target_display_name} 상품에도 적용 가능한 쿠폰을 확인했어요.",
                *[f"- {name}" for name in applicable_coupon_names[:5]],
            ]
        else:
            product_label = matched_product_name or target_display_name
            lines = [
                f"보유 쿠폰 기준으로 {product_label} 패턴에 적용 가능한 쿠폰을 확인했어요.",
                *[f"- {name}" for name in applicable_coupon_names[:5]],
            ]
        if len(applicable_coupon_names) > 5:
            lines.append(f"외 {len(applicable_coupon_names) - 5}개 쿠폰이 더 있어요.")
        if not target_brand:
            lines.append("정확한 최종 혜택가는 차량이나 타이어 사이즈를 선택한 뒤 확인할 수 있어요.")
    else:
        if target_brand:
            lines = [
                f"보유 쿠폰 기준 적용 가능 상품 목록에서 {target_display_name} 상품은 확인되지 않았어요.",
                "쿠폰함에서 상세 적용 조건을 확인해 주세요.",
            ]
        else:
            lines = [
                f"보유 쿠폰 중 {target_display_name} 패턴에 바로 적용 가능한 쿠폰은 확인되지 않았어요.",
                "쿠폰함의 적용 조건이나 진행 중인 이벤트를 다시 확인해 주세요.",
            ]
    quick_replies = (
        [
            {"label": "쿠폰함 바로가기", "url": CTAUrls.MY_COUPON_LIST_PC, "domain": "TRANSACTION"},
            {"label": "내 쿠폰 조회", "domain": "TRANSACTION"},
            {"label": "적용 상품 다시 확인", "domain": "TRANSACTION"},
        ]
        if target_brand
        else [
            {"label": "보유차량 중 선택", "domain": "DISCOVERY"},
            {"label": "사이즈 직접 입력", "domain": "DISCOVERY"},
            {"label": "내 쿠폰 조회", "domain": "TRANSACTION"},
        ]
    )
    predicted_domains = ["TRANSACTION"] if target_brand else ["DISCOVERY", "TRANSACTION"]

    return {
        "type": "data",
        "template": "quickReply",
        "source_domain": "transaction",
        "assistant_response_source": "code_product_coupon_resolver",
        "data": {
            "assistantResponse": "\n".join(lines),
            "quickReplies": quick_replies,
            "predictedDomains": predicted_domains,
        },
    }

def _is_strong_coupon_applicability_query(user_text: str) -> bool:
    if is_product_coupon_price_amount_query(user_text):
        return False
    frame = build_price_intent_frame(user_text)
    if _COUPON_ISSUE_INTENT_RE.search(user_text):
        return False
    if frame.intent in {"coupon_issue_request", "nonexistent_benefit"}:
        return False
    return frame.intent == "coupon_applicable_products"

def _is_product_coupon_eligibility_query(user_text: str) -> bool:
    frame = build_price_intent_frame(user_text)
    if _COUPON_ISSUE_INTENT_RE.search(user_text):
        return False
    if frame.intent in {"coupon_issue_request", "nonexistent_benefit"}:
        return False
    return frame.intent == "product_coupon_eligibility" and bool(frame.entities.get("product_name"))

def coupon_rows_from_my_coupons(tool_result: dict) -> list[dict]:
    return _coupon_rows_from_my_coupons(tool_result)

def chunk_coupon_numbers(cpn_nos: list[str], *, batch_size: int = 10) -> list[list[str]]:
    return _chunk_coupon_numbers(cpn_nos, batch_size=batch_size)

def merge_coupon_applicable_products_results(results: list[dict]) -> dict:
    return _merge_coupon_applicable_products_results(results)

def is_owned_coupon_expiry_lookup_query(user_text: str) -> bool:
    return _is_owned_coupon_expiry_lookup_query(user_text)

def build_owned_coupon_expiry_lookup_event(user_text: str, tool_result: dict) -> dict:
    return _build_owned_coupon_expiry_lookup_event(user_text, tool_result)

def is_owned_coupon_best_discount_query(user_text: str) -> bool:
    return _is_owned_coupon_best_discount_query(user_text)

def is_specific_owned_coupon_lookup_query(user_text: str) -> bool:
    return _is_specific_owned_coupon_lookup_query(user_text)

def specific_owned_coupon_lookup_hint(user_text: str) -> str | None:
    return _specific_owned_coupon_lookup_hint(user_text)

def owned_coupon_lookup_summary_text(user_text: str, tool_result: dict) -> str | None:
    return _owned_coupon_lookup_summary_text(user_text, tool_result)

def build_owned_coupon_best_discount_event(tool_result: dict) -> dict:
    return _build_owned_coupon_best_discount_event(tool_result)

def find_coupon_from_owned_coupons(user_text: str, tool_result: dict) -> dict | None:
    return _find_coupon_from_owned_coupons(user_text, tool_result)

def find_single_confident_coupon_from_owned_coupons(user_text: str, tool_result: dict) -> tuple[dict | None, list[dict]]:
    return _find_single_confident_coupon_from_owned_coupons(user_text, tool_result)

def coupon_channel_type(row: dict) -> str:
    return _coupon_channel_type(row)

def build_coupon_match_failure_event(user_text: str, candidate_rows: list[dict] | None = None) -> dict:
    return _build_coupon_match_failure_event(user_text, candidate_rows)

def build_coupon_channel_policy_event(
    coupon_row: dict,
    *,
    applicable_result: dict | None = None,
    target_product_name: str | None = None,
) -> dict | None:
    return _build_coupon_channel_policy_event(
        coupon_row,
        applicable_result=applicable_result,
        target_product_name=target_product_name,
    )

def build_coupon_applicability_event(
    tool_result: dict,
    coupon_row: dict,
    *,
    target_product_name: str | None = None,
    target_brand: dict | None = None,
) -> dict:
    return _build_coupon_applicability_event(
        tool_result,
        coupon_row,
        target_product_name=target_product_name,
        target_brand=target_brand,
    )

def build_product_coupon_eligibility_event(
    tool_result: dict,
    coupon_rows: list[dict],
    *,
    target_product_name: str,
    target_brand: dict | None = None,
) -> dict:
    return _build_product_coupon_eligibility_event(
        tool_result,
        coupon_rows,
        target_product_name=target_product_name,
        target_brand=target_brand,
    )
