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

    ``field`` is one of ``"price"``, ``"goods_no"``, ``"shop_id"``.
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
# tire_size_1 is the canonical field in source_filter.py; tire_size is a legacy
# alias still seen in some tool outputs.
_TIRE_SIZE_FIELDS: frozenset[str] = frozenset({"tire_size_1", "tire_size", "tireSize"})


def _walk(obj: Any, found: set, fields: frozenset[str], coerce):
    """Recursively walk a JSON-like structure, collecting values from ``fields``."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in fields:
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
