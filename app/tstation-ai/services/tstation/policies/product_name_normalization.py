"""Product name normalization for BE search and V3 slot state."""

from __future__ import annotations

import re
from typing import Any, Mapping


_PRODUCT_SEARCH_KEYWORD_OVERRIDES = {
    "kinergyex": "키너지 EX",
    "ventusairs": "벤투스 에어S",
    "벤투스airs": "벤투스 에어S",
    "벤투스에어s": "벤투스 에어S",
    "ventuss2": "벤투스 S2",
    "ventuss2as": "벤투스 S2 AS",
    "ventuss1evozas": "벤투스 S1 evo Z AS",
    "ventuss1evoz": "벤투스 S1 evo Z",
    "dynaprohpx": "다이나프로 HPX",
    "dynaprohp3": "다이나프로 HP3",
    "sfitas": "S FIT AS",
    "sfit": "S FIT",
    "ionevoassuv": "아이온 에보 AS SUV",
    "ionevoas": "아이온 에보 AS",
    "ionevo": "아이온 에보",
    "optimo": "옵티모",
    "michelincc2": "미쉐린 CC2",
    "mileageplus": "마일리지",
    "mileageplus2": "마일리지 플러스 2",
    "mileageplus3": "마일리지 플러스 3",
}

_PRODUCT_SLOT_KEYS = ("product_name", "tire_model", "pending_product_name")


def product_name_match_key(value: object) -> str:
    """Compact product text for alias matching."""

    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(value or "")).lower()


def preferred_product_search_keyword(product_name: object) -> str:
    """Return the BE-searchable Korean keyword for known aliases."""

    raw = str(product_name or "").strip()
    if not raw:
        return ""
    return _PRODUCT_SEARCH_KEYWORD_OVERRIDES.get(product_name_match_key(raw), raw)


def normalize_product_search_tool_args(args: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize search keyword arguments without changing unrelated tool args."""

    patch = {str(key): value for key, value in dict(args or {}).items()}
    keyword = preferred_product_search_keyword(patch.get("keyword"))
    if keyword:
        patch["keyword"] = keyword
    return patch


def normalize_product_slot_values(values: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize product-bearing slot values before they are persisted."""

    normalized = {str(key): value for key, value in dict(values or {}).items()}
    for key in _PRODUCT_SLOT_KEYS:
        if key in normalized:
            keyword = preferred_product_search_keyword(normalized.get(key))
            if keyword:
                normalized[key] = keyword
    return normalized
