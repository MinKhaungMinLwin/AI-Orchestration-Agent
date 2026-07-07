from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class StoreSearchFilters:
    svc_codes: tuple[str, ...] = ()
    all_my_t_only: bool = False
    imported_car_only: bool = False
    ev_specialty_only: bool = False
    ev_charge_available_only: bool = False

    def to_tool_args(self) -> dict[str, object]:
        args: dict[str, object] = {}
        if self.svc_codes:
            args["svc_codes"] = list(self.svc_codes)
        if self.all_my_t_only:
            args["all_my_t_only"] = True
        if self.imported_car_only:
            args["imported_car_only"] = True
        if self.ev_specialty_only:
            args["ev_specialty_only"] = True
        if self.ev_charge_available_only:
            args["ev_charge_available_only"] = True
        return args


_STORE_SEARCH_FILTER_PATTERNS: tuple[tuple[re.Pattern[str], StoreSearchFilters], ...] = (
    (
        re.compile(r"전기차\s*(?:특화|전문)|EV\s*(?:특화|전문)|전기차\s*특화매장|EV\s*특화매장", re.IGNORECASE),
        StoreSearchFilters(ev_specialty_only=True),
    ),
    (
        re.compile(r"전기차\s*충전|EV\s*충전|충전\s*가능", re.IGNORECASE),
        StoreSearchFilters(ev_charge_available_only=True),
    ),
    (
        re.compile(r"수입차\s*(?:특화|전문)|외제차\s*(?:특화|전문)", re.IGNORECASE),
        StoreSearchFilters(imported_car_only=True),
    ),
    (
        re.compile(r"올마이티|올마이T|all\s*my\s*t|무상\s*점검|무료\s*점검", re.IGNORECASE),
        StoreSearchFilters(all_my_t_only=True, svc_codes=("126",)),
    ),
    (
        re.compile(r"보관|타이어\s*호텔|윈터\s*타이어|겨울\s*타이어", re.IGNORECASE),
        StoreSearchFilters(svc_codes=("119",)),
    ),
    (
        re.compile(r"얼라인먼트|휠\s*얼라이먼트|휠\s*얼라인먼트", re.IGNORECASE),
        StoreSearchFilters(svc_codes=("124", "125")),
    ),
    (
        re.compile(r"경정비|엔진\s*오일|엔진오일|실내\s*필터|필터|와이퍼", re.IGNORECASE),
        StoreSearchFilters(svc_codes=("121", "122")),
    ),
    (
        re.compile(r"배터리", re.IGNORECASE),
        StoreSearchFilters(svc_codes=("116",)),
    ),
    (
        re.compile(r"수입\s*타이어", re.IGNORECASE),
        StoreSearchFilters(svc_codes=("120",)),
    ),
)


def resolve_store_search_filters(store_attribute: str | None) -> StoreSearchFilters | None:
    text = str(store_attribute or "").strip()
    if not text:
        return None
    for pattern, filters in _STORE_SEARCH_FILTER_PATTERNS:
        if pattern.search(text):
            return filters
    return None
