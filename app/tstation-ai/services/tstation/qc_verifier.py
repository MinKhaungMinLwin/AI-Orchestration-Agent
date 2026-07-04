"""Deterministic QC verifier for tstation chatbot drafts.

Replaces the LLM-based QC agent (g_qc_agent) that suffered from a high
false-positive rate when rewriting agent drafts.

Mission (per client spec): catch wrong prices, wrong product IDs, and wrong
store IDs that the domain agent may have hallucinated, by comparing the draft
text against the raw tool outputs captured during the same turn.

Design choices:
- Conservative: only flag a value when no plausible interpretation links it to
  source data. False-positive rate target = 0 (the original LLM QC's pain
  point).
- Pure / synchronous: no LLM call. Adds ~1-5 ms latency vs the ~300-500 ms LLM
  call it replaces.
- Pass-through by default: callers log mismatches but do not rewrite the draft.
  Rewriting is unsafe without context the verifier does not have (slot scope,
  prior-turn cards, computed prices). Set ``AI_QC_STRICT_MODE`` (future) to
  escalate to a fallback message instead.

Scope (v1):
- Prices: integer won values (₩123,456 or 123,456원). Matches direct quotes
  from source plus simple arithmetic combinations (qty x unit for qty 1..12,
  /2 for 1+1, /4 for 2+2, sum of two source values for "상품가 + 공임비").
- goods_no: ``G`` + 12 digits, exact set membership.
- shop_id: ``C`` + 5 digits or ``F`` + 6 digits, exact set membership.
- tire_size: ``235/55R19`` / ``225/45ZR17`` / ``LT235/85R16`` style.
  Customer-safety-critical fact; pattern is unambiguous.

Anything else (prose, scope claims, descriptions, free-form names, percentages,
distances, ratings, dates) is intentionally out of scope — those were the
false-positive vectors in the LLM QC. Add carefully once log data justifies it.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Patterns
# --------------------------------------------------------------------------- #

# ₩123,456 | 123,456원 | 123456원
_PRICE_PATTERNS = (
    re.compile(r"₩\s*(\d{1,3}(?:,\d{3})+|\d{4,})"),
    re.compile(r"(\d{1,3}(?:,\d{3})+|\d{4,})\s*원"),
)

_GOODS_NO_PATTERN = re.compile(r"\bG\d{12}\b")
_SHOP_ID_PATTERN = re.compile(r"\b(?:C\d{5}|F\d{6})\b")

# Tire-size literals: width / aspect-ratio + optional speed rating (Z) + R + inch.
# Matches "235/55R19", "225/45ZR17", "LT235/85R16". Load/speed index that often
# follows ("235/55R19 95H") is intentionally not part of the canonical token —
# verifier only checks the core size string.
_TIRE_SIZE_PATTERN = re.compile(
    r"\b(?:LT)?\d{2,3}/\d{2}Z?R\d{2}\b",
    re.IGNORECASE,
)
_INVENTORY_UNAVAILABLE_PATTERNS = (
    re.compile(r"(?:재고|장착|예약|오늘\s*서비스|오늘\s*장착).{0,16}(?:없|불가|어렵|확인(?:할\s*수)?\s*없|확인.*못)"),
    re.compile(r"(?:확인(?:할\s*수)?\s*없|확인.*못).{0,16}(?:재고|장착|예약|매장)"),
    re.compile(r"(?:가능한|가능)\s*(?:매장|일정|재고).{0,16}(?:없|찾지\s*못|확인.*못)"),
)

# Skip integers below this threshold as candidate prices — they are usually
# quantities, ratings, percentages, or page numbers, not won amounts.
_MIN_PRICE = 1000

# Cap qty multiplier scan to avoid combinatorial explosion on adversarial source.
_MAX_QTY_MULTIPLIER = 12


# --------------------------------------------------------------------------- #
#  Data classes
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Mismatch:
    """A factual mismatch detected between the draft and the source data.

    ``field`` is one of ``"price"``, ``"goods_no"``, ``"shop_id"``,
    ``"tire_size"``, or ``"inventory_availability"``.
    ``value`` is the literal substring as it appears in the draft.
    """

    field: str
    value: str

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "value": self.value}


# --------------------------------------------------------------------------- #
#  Source value collectors
# --------------------------------------------------------------------------- #

# Field names that carry won prices across tools. Keep this list explicit —
# adding a new key requires a deliberate decision so we know the verifier covers it.
_PRICE_FIELDS: frozenset[str] = frozenset({
    "sale_prc",
    "final_prc",
    "extra_fvr_sale_prc",
    "cheapest_final_prc",
    "cheapest_total_discount",
    "discount_amt",
    "final_unit_price",
    "originalPrice",
    "original_price",
    "price",
    "unit_price",
    "total_discount",
    "payment_amount",
    "paymentAmount",
    "labor_cost",
})

_GOODS_NO_FIELDS: frozenset[str] = frozenset({"goods_no", "goodsNo"})
_SHOP_ID_FIELDS: frozenset[str] = frozenset({"shop_id", "shopId"})
# tire_size_1 is the canonical scalar field in source_filter.py; tire_size is a
# legacy alias still seen in some tool outputs. available_sizes is a list field
# used by unsized search_product responses.
_TIRE_SIZE_FIELDS: frozenset[str] = frozenset({"tire_size_1", "tire_size", "tireSize", "available_sizes"})
_PRODUCT_ROW_TOOLS: frozenset[str] = frozenset({
    "search_product_summary_tool",
    "search_product_tool",
    "get_products_recommendations_tool",
    "get_best_selling_products_tool",
    "get_product_description_tool",
})
_BRAND_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "HK": ("hankook", "한국", "한국타이어"),
    "MC": ("michelin", "미쉐린"),
    "CT": ("continental", "콘티넨탈"),
    "BS": ("bridgestone", "브리지스톤"),
    "PI": ("pirelli", "피렐리"),
    "GY": ("goodyear", "굿이어"),
    "LF": ("laufenn", "라우펜"),
}
_RANKING_PRICE_FIELDS: tuple[str, ...] = ("cheapest_final_prc", "extra_fvr_sale_prc", "sale_prc")
_RANKING_METRIC_FIELDS: dict[str, tuple[str, ...]] = {
    "price": _RANKING_PRICE_FIELDS,
    "review": ("review_count",),
    "rating": ("rating_avg", "rate"),
    "release": ("t_rls_yearmon", "sys_reg_dtime"),
    "noise": ("label_pndb", "label_pnwave", "t_silence"),
    "wet": ("wet",),
    "snow": ("t_snow", "t_ice"),
    "grade": ("prc_grd_nm",),
    "vehicle_type": ("car_knd_nm",),
    "mileage": ("t_life_span", "t_tray_ware"),
}
_GRADE_ORDER = {"이코노미": 1, "스탠다드": 2, "프리미엄": 3}


def _walk(obj: Any, found: set, fields: frozenset[str], coerce):
    """Recursively walk a JSON-like structure, collecting values from ``fields``."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in fields:
                if isinstance(value, list):
                    for item in value:
                        coerced = coerce(item)
                        if coerced is not None:
                            found.add(coerced)
                else:
                    coerced = coerce(value)
                    if coerced is not None:
                        found.add(coerced)
            else:
                _walk(value, found, fields, coerce)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item, found, fields, coerce)


def _as_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= _MIN_PRICE:
        return int(value)
    return None


def _as_pattern_string(pattern: re.Pattern[str]):
    def coerce(value: Any) -> str | None:
        if isinstance(value, str) and pattern.fullmatch(value):
            return value
        return None
    return coerce


def collect_source_values(structured_sources: Iterable[tuple[str, Any]]) -> dict[str, set]:
    """Collect all valid prices, goods_no, and shop_ids from tool outputs.

    Args:
        structured_sources: Iterable of ``(tool_name, parsed_output_dict)``.

    Returns:
        Dict with keys ``"prices"`` (set[int]), ``"goods_no"`` (set[str]),
        ``"shop_ids"`` (set[str]), ``"tire_sizes"`` (set[str], uppercased).
    """
    prices: set[int] = set()
    goods_no: set[str] = set()
    shop_ids: set[str] = set()
    tire_sizes: set[str] = set()
    for _tool, output in structured_sources:
        _walk(output, prices, _PRICE_FIELDS, _as_positive_int)
        _walk(output, goods_no, _GOODS_NO_FIELDS, _as_pattern_string(_GOODS_NO_PATTERN))
        _walk(output, shop_ids, _SHOP_ID_FIELDS, _as_pattern_string(_SHOP_ID_PATTERN))
        _walk(output, tire_sizes, _TIRE_SIZE_FIELDS, _as_normalized_tire_size)
    return {
        "prices": prices,
        "goods_no": goods_no,
        "shop_ids": shop_ids,
        "tire_sizes": tire_sizes,
    }


def _nested_value(obj: Any, path: tuple[str, ...]) -> Any:
    current = obj
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _non_empty_list_at(obj: Any, *paths: tuple[str, ...]) -> bool:
    for path in paths:
        value = _nested_value(obj, path)
        if isinstance(value, list) and value:
            return True
    return False


def _has_preview_schedule_slots(output: Any) -> bool:
    stores = _nested_value(output, ("data", "schedule", "stores"))
    if not isinstance(stores, list):
        stores = _nested_value(output, ("schedule", "stores"))
    if not isinstance(stores, list):
        return False
    for store in stores:
        if isinstance(store, dict) and isinstance(store.get("slots"), list) and store.get("slots"):
            return True
    return False


def _has_tool_backed_available_inventory(structured_sources: Iterable[tuple[str, Any]]) -> bool:
    """Return True only when inventory/preview tools provide installable candidates."""
    for tool_name, output in structured_sources:
        if not isinstance(output, dict):
            continue
        if tool_name == "transaction_store_preview_tool":
            if _non_empty_list_at(
                output,
                ("data", "inventory", "todayShopArray"),
                ("data", "inventory", "tnaShopArray"),
                ("data", "stores"),
                ("inventory", "todayShopArray"),
                ("inventory", "tnaShopArray"),
                ("stores",),
            ):
                return True
            if _has_preview_schedule_slots(output):
                return True
        elif tool_name == "get_store_inventory_tool" and _non_empty_list_at(
            output,
            ("data", "todayShopArray"),
            ("data", "tnaShopArray"),
            ("todayShopArray",),
            ("tnaShopArray",),
        ):
            return True
    return False


def _as_normalized_tire_size(value: Any) -> str | None:
    """Coerce a source tire-size value to its canonical uppercase form.

    Tolerates lowercase ``r`` and surrounding whitespace so source quirks
    like "235/55r19" or " 225/45R17 " still match the draft literal.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip().upper()
    if _TIRE_SIZE_PATTERN.fullmatch(candidate):
        return candidate
    return None


# --------------------------------------------------------------------------- #
#  Draft extractors
# --------------------------------------------------------------------------- #

def _extract_price_literals(draft: str) -> list[str]:
    """Extract price literals preserving original formatting (for mismatch reports)."""
    seen: set[str] = set()
    out: list[str] = []
    for pattern in _PRICE_PATTERNS:
        for match in pattern.finditer(draft):
            literal = match.group(0).strip()
            if literal not in seen:
                seen.add(literal)
                out.append(literal)
    return out


def _normalize_price_literal(literal: str) -> int | None:
    digits = re.sub(r"[^\d]", "", literal)
    return int(digits) if digits else None


def _claims_inventory_unavailable(draft: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(draft or "")).strip()
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _INVENTORY_UNAVAILABLE_PATTERNS)


def _source_product_rows(structured_sources: Iterable[tuple[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tool_name, output in structured_sources:
        if tool_name not in _PRODUCT_ROW_TOOLS or not isinstance(output, dict):
            continue
        data = output.get("data")
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            candidates = data.get("items") or []
        elif isinstance(data, list):
            candidates = data
        else:
            candidates = [data] if isinstance(data, dict) else []
        for row in candidates:
            if isinstance(row, dict) and str(row.get("goods_nm") or row.get("titleProductName") or "").strip():
                rows.append(row)
    return rows


def _row_matches_brand(row: dict[str, Any], expected_brand_cd: str) -> bool | None:
    expected = str(expected_brand_cd or "").strip().upper()
    if not expected:
        return None
    row_brand_cd = str(row.get("brand_cd") or row.get("brandCode") or "").strip().upper()
    if row_brand_cd:
        return row_brand_cd == expected
    hints = _BRAND_NAME_HINTS.get(expected, ())
    if not hints:
        return None
    haystack = " ".join(
        str(row.get(field) or "")
        for field in ("brand_nm", "brand_name", "brandName", "goods_nm", "titleProductName", "title")
    ).casefold()
    if not haystack:
        return None
    if any(hint.casefold() in haystack for hint in hints):
        return True
    known_other_hints = {
        hint.casefold()
        for brand_cd, brand_hints in _BRAND_NAME_HINTS.items()
        if brand_cd != expected
        for hint in brand_hints
    }
    if any(hint in haystack for hint in known_other_hints):
        return False
    return None


def _brand_mismatches(
    structured_sources: Iterable[tuple[str, Any]],
    *,
    expected_brand_cd: str | None,
) -> list[Mismatch]:
    expected = str(expected_brand_cd or "").strip().upper()
    if not expected:
        return []
    mismatches: list[Mismatch] = []
    for row in _source_product_rows(structured_sources):
        matches = _row_matches_brand(row, expected)
        if matches is not False:
            continue
        name = _row_product_name(row)
        row_brand = str(row.get("brand_cd") or row.get("brand_nm") or row.get("brandName") or "").strip()
        mismatches.append(Mismatch(field="brand", value=f"expected={expected};row={row_brand or name}"))
    return mismatches


def _coerce_rank_value(value: Any) -> float | str | None:
    if isinstance(value, bool) or value in (None, "", [], {}):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        digits = re.sub(r"[^\d.]", "", stripped)
        if digits:
            try:
                return float(digits)
            except ValueError:
                pass
        return stripped
    return None


def _ranking_value(row: dict[str, Any], metric: str, price_basis: str | None = None) -> float | str | None:
    fields = _RANKING_METRIC_FIELDS.get(metric)
    if not fields:
        return None
    if metric == "price" and price_basis in _RANKING_PRICE_FIELDS:
        fields = (price_basis, *tuple(field for field in fields if field != price_basis))
    for field in fields:
        value = _coerce_rank_value(row.get(field))
        if value is not None:
            if metric == "grade" and isinstance(value, str):
                return float(_GRADE_ORDER.get(value, 0)) if value in _GRADE_ORDER else value
            return value
    return None


def _best_ranking_rows(
    rows: list[dict[str, Any]],
    *,
    metric: str,
    direction: str,
    price_basis: str | None = None,
) -> list[dict[str, Any]]:
    scored: list[tuple[float | str, dict[str, Any]]] = []
    for row in rows:
        value = _ranking_value(row, metric, price_basis=price_basis)
        if value is not None:
            scored.append((value, row))
    if not scored:
        return []
    numeric = [(value, row) for value, row in scored if isinstance(value, float)]
    if numeric:
        if metric in {"price", "noise"} or direction == "min":
            best_value = min(value for value, _row in numeric)
        else:
            best_value = max(value for value, _row in numeric)
        return [row for value, row in numeric if value == best_value]
    if direction == "match":
        return [row for _value, row in scored]
    return []


def _row_product_name(row: dict[str, Any]) -> str:
    return str(row.get("goods_nm") or row.get("titleProductName") or row.get("title") or "").strip()


def _ranking_mismatches(
    draft: str,
    structured_sources: Iterable[tuple[str, Any]],
    *,
    ranking_metric: str | None,
    ranking_direction: str | None,
    ranking_price_basis: str | None,
) -> list[Mismatch]:
    metric = str(ranking_metric or "").strip()
    if metric not in _RANKING_METRIC_FIELDS:
        return []
    rows = _source_product_rows(structured_sources)
    if len(rows) < 2:
        return []
    direction = str(ranking_direction or "").strip() or ("min" if metric in {"price", "noise"} else "max")
    best_rows = _best_ranking_rows(rows, metric=metric, direction=direction, price_basis=ranking_price_basis)
    if not best_rows:
        return []
    expected_names = {_row_product_name(row) for row in best_rows if _row_product_name(row)}
    mentioned_names = {
        name
        for row in rows
        if (name := _row_product_name(row)) and name.casefold() in draft.casefold()
    }
    if not mentioned_names or mentioned_names & expected_names:
        return []
    return [
        Mismatch(
            field="recent_product_set_ranking",
            value=f"{metric}:expected={','.join(sorted(expected_names))};mentioned={','.join(sorted(mentioned_names))}",
        )
    ]


# --------------------------------------------------------------------------- #
#  Arithmetic explanation
# --------------------------------------------------------------------------- #

def _is_price_explainable(value: int, source_prices: set[int]) -> bool:
    """Return True when ``value`` matches a source price or a simple combination.

    Combinations covered:
    - Direct: ``value in source_prices``
    - qty x unit for qty in 1..12 (e.g., 4-tire total)
    - unit / 2 (1+1 per-unit) and unit / 4 (2+2 per-unit) — exact division only
    - sum of any 2 source prices (e.g., product + labor cost)
    """
    if value in source_prices:
        return True
    for unit in source_prices:
        for qty in range(2, _MAX_QTY_MULTIPLIER + 1):
            if value == unit * qty:
                return True
        if unit % 2 == 0 and value == unit // 2:
            return True
        if unit % 4 == 0 and value == unit // 4:
            return True
    prices_list = list(source_prices)
    for i in range(len(prices_list)):
        for j in range(i + 1, len(prices_list)):
            if value == prices_list[i] + prices_list[j]:
                return True
    return False


# --------------------------------------------------------------------------- #
#  Entry point
# --------------------------------------------------------------------------- #

def verify_draft(
    draft: str,
    structured_sources: Iterable[tuple[str, Any]],
    *,
    ranking_metric: str | None = None,
    ranking_direction: str | None = None,
    ranking_price_basis: str | None = None,
    expected_brand_cd: str | None = None,
) -> list[Mismatch]:
    """Verify factual claims in the draft against the structured tool outputs.

    Returns an empty list when the draft passes (no detectable mismatch). A
    non-empty list signals at least one provable mismatch — callers may log,
    block, or warn based on policy.

    The verifier is conservative: when uncertain (e.g., draft has no prices at
    all, or source contains no prices to check against), it returns an empty
    list rather than guessing.
    """
    if not draft:
        return []
    sources = list(structured_sources)
    if not sources:
        return []

    values = collect_source_values(sources)
    valid_prices: set[int] = values["prices"]
    valid_goods: set[str] = values["goods_no"]
    valid_shops: set[str] = values["shop_ids"]
    valid_sizes: set[str] = values["tire_sizes"]

    mismatches: list[Mismatch] = []

    if valid_prices:
        for literal in _extract_price_literals(draft):
            value = _normalize_price_literal(literal)
            if value is None or value < _MIN_PRICE:
                continue
            if not _is_price_explainable(value, valid_prices):
                mismatches.append(Mismatch(field="price", value=literal))

    if valid_goods:
        for match in _GOODS_NO_PATTERN.finditer(draft):
            literal = match.group(0)
            if literal not in valid_goods:
                mismatches.append(Mismatch(field="goods_no", value=literal))

    if valid_shops:
        for match in _SHOP_ID_PATTERN.finditer(draft):
            literal = match.group(0)
            if literal not in valid_shops:
                mismatches.append(Mismatch(field="shop_id", value=literal))

    if valid_sizes:
        seen_sizes: set[str] = set()
        for match in _TIRE_SIZE_PATTERN.finditer(draft):
            literal = match.group(0)
            normalized = literal.upper()
            if normalized in seen_sizes:
                continue
            seen_sizes.add(normalized)
            if normalized not in valid_sizes:
                mismatches.append(Mismatch(field="tire_size", value=literal))

    if _has_tool_backed_available_inventory(sources) and _claims_inventory_unavailable(draft):
        mismatches.append(Mismatch(field="inventory_availability", value="tool_available_but_draft_unavailable"))

    mismatches.extend(
        _ranking_mismatches(
            draft,
            sources,
            ranking_metric=ranking_metric,
            ranking_direction=ranking_direction,
            ranking_price_basis=ranking_price_basis,
        )
    )
    mismatches.extend(_brand_mismatches(sources, expected_brand_cd=expected_brand_cd))

    return mismatches


def parse_tool_output(raw: Any) -> dict | None:
    """Best-effort parse of a tool ``event.output`` payload to a dict.

    Tool events deliver outputs as JSON strings; some callers already pass a
    dict. Returns ``None`` when the payload is neither a parseable JSON object
    nor a dict.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
        if isinstance(parsed, dict):
            return parsed
    return None
