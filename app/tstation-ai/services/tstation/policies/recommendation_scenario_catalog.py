"""Catalog-backed recommendation scenario contracts.

The LLM/router may classify a user turn into a catalog key, but tool arguments
must come from this module so identical requests produce identical conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping


@dataclass(frozen=True)
class RecommendationScenario:
    key: str
    expressions: tuple[re.Pattern[str], ...]
    tool_args_patch: Mapping[str, Any]
    response_label: str
    approximation: bool = False
    approximation_basis: str | None = None


def _patterns(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


RECOMMENDATION_SCENARIO_CATALOG: dict[str, RecommendationScenario] = {
    "value": RecommendationScenario(
        key="value",
        expressions=_patterns(r"가성비|합리적|가격\s*대비|value"),
        tool_args_patch={"rcmd_type": "value"},
        response_label="가성비",
    ),
    "discount": RecommendationScenario(
        key="discount",
        expressions=_patterns(r"할인|세일|할인율"),
        tool_args_patch={"rcmd_type": "discount"},
        response_label="할인",
    ),
    "wet": RecommendationScenario(
        key="wet",
        expressions=_patterns(r"빗길|젖은\s*노면|젖은노면|wet|비\s*오는"),
        tool_args_patch={"rcmd_type": "wet"},
        response_label="빗길",
    ),
    "snow": RecommendationScenario(
        key="snow",
        expressions=_patterns(r"눈길|겨울|윈터|winter|스노우|snow"),
        tool_args_patch={"rcmd_type": "snow", "season_nm": "겨울"},
        response_label="겨울/눈길",
    ),
    "high_speed": RecommendationScenario(
        key="high_speed",
        expressions=_patterns(r"고속|고속도로|high\s*speed"),
        tool_args_patch={"rcmd_type": "high_speed"},
        response_label="고속 주행",
    ),
    "handling": RecommendationScenario(
        key="handling",
        expressions=_patterns(r"핸들링|코너링|제동|브레이크|handling|braking"),
        tool_args_patch={"rcmd_type": "performance"},
        response_label="핸들링",
    ),
    "low_vibration": RecommendationScenario(
        key="low_vibration",
        expressions=_patterns(r"저소음|정숙|조용|소음|진동"),
        tool_args_patch={"rcmd_type": "low_vibration"},
        response_label="정숙/저진동",
    ),
    "performance": RecommendationScenario(
        key="performance",
        expressions=_patterns(r"퍼포먼스|고성능|스포츠|performance"),
        tool_args_patch={"rcmd_type": "performance"},
        response_label="퍼포먼스",
    ),
    "commute": RecommendationScenario(
        key="commute",
        expressions=_patterns(r"출퇴근|통근|commute"),
        tool_args_patch={"rcmd_type": "commute"},
        response_label="출퇴근",
    ),
    "long_distance": RecommendationScenario(
        key="long_distance",
        expressions=_patterns(r"장거리|long\s*distance|마일리지|수명|오래\s*(?:타|가)|내구|마모\s*(?:강|적|덜)"),
        tool_args_patch={"rcmd_type": "long_distance"},
        response_label="장거리",
    ),
    "urban": RecommendationScenario(
        key="urban",
        expressions=_patterns(r"도심|시내|urban"),
        tool_args_patch={"rcmd_type": "urban"},
        response_label="도심 주행",
    ),
    "family": RecommendationScenario(
        key="family",
        expressions=_patterns(r"패밀리|가족|승차감|컴포트|comfort"),
        tool_args_patch={"rcmd_type": "family"},
        response_label="가족/승차감",
    ),
    "safe_kids": RecommendationScenario(
        key="safe_kids",
        expressions=_patterns(
            r"키즈|어린이|유아|아이\s*(?:태우|동승|와\s*함께|랑\s*타|안전|보호)|"
            r"안전(?:한|하게|성|하게\s*탈|하게\s*타|.*(?:아이|어린이|유아|가족))"
        ),
        tool_args_patch={"rcmd_type": "safe_kids"},
        response_label="아이/안전",
    ),
    "ev": RecommendationScenario(
        key="ev",
        expressions=_patterns(r"전기차|전기차용|electric|테슬라|모델\s*Y|모델Y|(?<![A-Za-z])EV(?![A-Za-z])"),
        tool_args_patch={"vehicle_type": "ev"},
        response_label="전기차",
    ),
    "suv": RecommendationScenario(
        key="suv",
        expressions=_patterns(r"SUV|스포츠\s*유틸리티"),
        tool_args_patch={"vehicle_type": "suv"},
        response_label="SUV",
    ),
    "heavy_load": RecommendationScenario(
        key="heavy_load",
        expressions=_patterns(r"고하중|하중|무거운\s*짐|화물차|트럭|밴|승합차"),
        tool_args_patch={"rcmd_type": "heavy_load"},
        response_label="하중 안정성",
    ),
    "all_season": RecommendationScenario(
        key="all_season",
        expressions=_patterns(r"사계절|올시즌|all\s*season"),
        tool_args_patch={"rcmd_type": "all_weather", "season_nm": "사계절"},
        response_label="사계절",
    ),
    "all_weather": RecommendationScenario(
        key="all_weather",
        expressions=_patterns(r"올웨더|전천후|all\s*weather"),
        tool_args_patch={"rcmd_type": "all_weather", "season_nm": "올웨더"},
        response_label="올웨더",
    ),
    "sound_absorber": RecommendationScenario(
        key="sound_absorber",
        expressions=_patterns(r"흡음재|흡음|sound\s*absorber|소음\s*저감"),
        tool_args_patch={"rcmd_type": "sound_absorber"},
        response_label="흡음재",
    ),
    "runflat": RecommendationScenario(
        key="runflat",
        expressions=_patterns(r"런플랫|run\s*flat|runflat"),
        tool_args_patch={"rcmd_type": "tstation", "pfm_nm": "RUNFLAT"},
        response_label="런플랫",
    ),
    "offroad": RecommendationScenario(
        key="offroad",
        expressions=_patterns(r"오프\s*로드|험로|비포장|비포장\s*도로|캠핑\s*SUV|차박"),
        tool_args_patch={"rcmd_type": "heavy_load", "vehicle_type": "suv"},
        response_label="오프로드/비포장 주행",
        approximation=True,
        approximation_basis="SUV/하중 안정성",
    ),
}

SUPPORTED_RECOMMENDATION_SCENARIOS = frozenset(RECOMMENDATION_SCENARIO_CATALOG)
_SCENARIO_MATCH_PRIORITY: tuple[str, ...] = (
    "offroad",
    "sound_absorber",
    "runflat",
    "all_weather",
    "all_season",
    "low_vibration",
    "performance",
    "handling",
    "heavy_load",
    "value",
    "discount",
    "wet",
    "snow",
    "high_speed",
    "commute",
    "long_distance",
    "urban",
    "family",
    "safe_kids",
    "ev",
    "suv",
)

_SCENARIO_ALIASES: dict[str, str] = {
    "mileage": "long_distance",
    "life_span": "long_distance",
    "lifespan": "long_distance",
}


def recommendation_scenario_from_text(text: str, router_scenario: str | None = None) -> RecommendationScenario | None:
    """Return a supported catalog scenario only when the current turn has a matching anchor."""

    normalized_router_scenario = str(router_scenario or "").strip().lower()
    if normalized_router_scenario in {"", "none", "unknown_scenario"}:
        normalized_router_scenario = ""
    normalized_router_scenario = _SCENARIO_ALIASES.get(normalized_router_scenario, normalized_router_scenario)
    if normalized_router_scenario in RECOMMENDATION_SCENARIO_CATALOG:
        scenario = RECOMMENDATION_SCENARIO_CATALOG[normalized_router_scenario]
        if any(pattern.search(text or "") for pattern in scenario.expressions):
            return scenario

    for key in _SCENARIO_MATCH_PRIORITY:
        scenario = RECOMMENDATION_SCENARIO_CATALOG[key]
        if any(pattern.search(text or "") for pattern in scenario.expressions):
            return scenario
    return None


def recommendation_scenario_metadata(scenario: RecommendationScenario) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "recommendation_scenario": scenario.key,
        "recommendation_scenario_label": scenario.response_label,
        "applied_rcmd_type": scenario.tool_args_patch.get("rcmd_type"),
        "applied_vehicle_type": scenario.tool_args_patch.get("vehicle_type"),
        "applied_season_nm": scenario.tool_args_patch.get("season_nm"),
    }
    if scenario.approximation:
        metadata["approximation"] = True
        metadata["approximation_basis"] = scenario.approximation_basis
    return {key: value for key, value in metadata.items() if value not in (None, "")}
