"""LLM gate for deciding whether a region query is usable in Korea.

Kakao place search is a keyword POI search, not a domestic-region validator.
This gate answers only whether the user's region_code can be used as a Korean
service-area / landmark search seed before trying Kakao coordinate fallback.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from textwrap import dedent
from typing import Literal

from langchain_litellm import ChatLiteLLM
from pydantic import BaseModel, Field

from config.env import settings

logger = logging.getLogger(__name__)

DomesticRegionKind = Literal[
    "domestic_region",
    "domestic_landmark",
    "foreign_region",
    "business_name",
    "unknown",
]


class DomesticRegionGateDecision(BaseModel):
    is_domestic_search_area: bool = Field(
        description="Whether this query can be used as a Korea domestic region/landmark search seed."
    )
    kind: DomesticRegionKind = Field(description="Classification of the query.")
    reason: str = Field(description="Short reason for logs/traces. Do not expose directly to users.")


_FOREIGN_REGION_QUERY_RE = re.compile(
    r"^(평양|북한|베이징|북경|상하이|상해|러시아|일본|중국|미국|대만|타이완|홍콩|마카오|"
    r"싱가포르|베트남|태국|방콕|도쿄|동경|오사카|교토|후쿠오카|파리|런던|독일|프랑스|유럽|"
    r"몽골|이탈리아|캐나다|하와이|괌)$",
    re.IGNORECASE,
)
_DOMESTIC_LANDMARK_SUFFIX_RE = re.compile(
    r"(역|구청|시청|군청|도청|터미널|공항|항구|IC|나들목|대교|시장|광장|공원|타워|몰|시티)$",
    re.IGNORECASE,
)


def deterministic_domestic_region_gate_decision(query: str | None) -> DomesticRegionGateDecision | None:
    text = (query or "").strip()
    if not text:
        return DomesticRegionGateDecision(
            is_domestic_search_area=False,
            kind="unknown",
            reason="Empty region query.",
        )
    if _FOREIGN_REGION_QUERY_RE.fullmatch(text):
        return DomesticRegionGateDecision(
            is_domestic_search_area=False,
            kind="foreign_region",
            reason="Known foreign or non-service-area region.",
        )
    if _DOMESTIC_LANDMARK_SUFFIX_RE.search(text):
        return DomesticRegionGateDecision(
            is_domestic_search_area=True,
            kind="domestic_landmark",
            reason="Looks like a Korean landmark or transport hub query.",
        )
    return None


@lru_cache(maxsize=1)
def _domestic_region_gate_model():
    llm = ChatLiteLLM(
        api_base=settings.AI_GATEWAY_BASE_URL,
        api_key=settings.AI_GATEWAY_API_KEY,
        model=f"{settings.AI_DEFAULT_PROVIDER}/{settings.AI_MODEL_MINI}",
        streaming=False,
        request_timeout=8,
    )
    return llm.with_structured_output(DomesticRegionGateDecision)


def decide_domestic_search_area(
    query: str | None,
    *,
    model=None,
) -> DomesticRegionGateDecision:
    """Decide whether `query` is a Korea domestic region/landmark.

    Fail closed: if the LLM cannot decide, block Kakao coordinate fallback so an
    overseas or business-name query cannot turn into an unrelated domestic store
    list.
    """
    deterministic = deterministic_domestic_region_gate_decision(query)
    if deterministic is not None:
        return deterministic

    text = (query or "").strip()
    prompt = dedent(f"""
    You are a pre-search safety gate for a Korean tire-commerce chatbot.

    Decide whether the user's input can be used as a Korea domestic region or
    domestic landmark for T'Station store search.

    Return true ONLY if the input is a place in South Korea that a customer
    would reasonably use for nearby store search, such as:
    - Korean administrative area: city, county, district, town, neighborhood
    - Korean landmark / transit hub: station, city hall, district office,
      airport, terminal, IC, well-known domestic area name

    Return false for:
    - countries or overseas cities/regions, including North Korea
    - business names, restaurant names, gas stations, cafes, hospitals, etc.
    - vague non-place words or unknown inputs

    Important examples:
    - 평양: false, foreign_region
    - 베이징: false, foreign_region
    - 러시아: false, foreign_region
    - 해운대: true, domestic_region
    - 광교: true, domestic_region
    - 강남구청: true, domestic_landmark
    - 서울역: true, domestic_landmark
    - 센텀시티: true, domestic_region

    User input:
    {text}
    """).strip()

    try:
        gate_model = model or _domestic_region_gate_model()
        decision = gate_model.invoke(prompt)
        if isinstance(decision, DomesticRegionGateDecision):
            return decision
        return DomesticRegionGateDecision.model_validate(decision)
    except Exception as exc:
        logger.warning("[DOMESTIC_REGION_GATE] LLM decision failed; blocking fallback: %s", exc)
        return DomesticRegionGateDecision(
            is_domestic_search_area=False,
            kind="unknown",
            reason="LLM gate failed; conservatively blocked region place fallback.",
        )
