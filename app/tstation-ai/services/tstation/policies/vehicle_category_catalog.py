"""Deterministic car-model-name -> vehicle-category inference catalog.

First-pass mapping for text-based vehicle recommendations ("G바겐 타이어 추천해줘"):
when the user names a car model without an explicit category keyword
(SUV/전기차/세단/트럭 -- those win upstream in ``discovery_intent_policy``), infer the
recommendation ``vehicle_type`` filter ("ev" | "suv" | "passenger" | "truck_van")
from the model name.

Design rules:
1. EV-only rule: only dedicated-EV models map to "ev". Models sold as both ICE and
   EV variants (코나, 니로, G80, GV70, etc.) map to their body type, so EV-specific
   products are recommended only on an explicit EV request.
2. Entry order matters: the first matching entry wins, so longer/more specific
   names must precede prefixes (렉스턴 스포츠 before 렉스턴).
3. ``masked_text`` blanks matched model mentions so scenario extraction ignores
   words that belong to the model name (스포츠 in 렉스턴 스포츠).
4. Latin/alphanumeric aliases use non-alphanumeric boundaries and flexible
   space/hyphen matching. Korean aliases match as substrings because particles
   attach directly.
5. Curated, not exhaustive. Unlisted models fall back to the Discovery agent's
   own model knowledge in the CAR MODEL DISPLAY flow.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class VehicleModelMatch(NamedTuple):
    model: str
    category: str  # "ev" | "suv" | "passenger" | "truck_van"
    masked_text: str
    matched_text: str
    vehicle_query: str


_LATIN_ALIAS_RE = re.compile(r"^[A-Za-z0-9 .\-]+$")


def _alias_pattern(alias: str) -> str:
    """Compile one alias into a regex fragment."""
    if alias.startswith("(?"):
        return alias
    body = r"[\s\-]*".join(re.escape(token) for token in re.split(r"[ \-]", alias) if token)
    if _LATIN_ALIAS_RE.match(alias):
        return rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])"
    return body


# (canonical model, category, aliases). Order = match priority; see rule 2.
_MODEL_ENTRIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # --- EV-only models (dedicated electric; dual-fuel models live under body type) ---
    ("테슬라", "ev", ("테슬라", "tesla")),
    ("테슬라 모델 3", "ev", ("모델 3", "model 3")),
    ("테슬라 모델 Y", "ev", ("모델 Y", "model y")),
    ("테슬라 모델 S", "ev", ("모델 S", "model s")),
    ("테슬라 모델 X", "ev", ("모델 X", "model x")),
    ("현대 아이오닉", "ev", ("아이오닉", "ioniq")),
    ("기아 EV 시리즈", "ev", ("EV3", "EV6", "EV9")),
    ("제네시스 GV60", "ev", ("GV60",)),
    ("벤츠 EQ 시리즈", "ev", ("EQS", "EQE", "EQA", "EQB", "EQC")),
    ("BMW i 시리즈", "ev", ("i4", "i5", "i7", "iX")),
    ("아우디 e-트론", "ev", ("e-tron", "이트론", "e트론")),
    ("폴스타", "ev", ("폴스타", "polestar")),
    ("포르쉐 타이칸", "ev", ("타이칸", "taycan")),
    # --- Light truck / van (before SUV so 렉스턴 스포츠 > 렉스턴) ---
    ("렉스턴 스포츠", "truck_van", ("렉스턴 스포츠",)),
    ("현대 포터", "truck_van", ("(?<!서)포터", "porter")),
    ("기아 봉고", "truck_van", ("봉고", "bongo")),
    ("현대 스타렉스", "truck_van", ("스타렉스", "starex")),
    ("현대 스타리아", "truck_van", ("스타리아", "staria")),
    ("현대 쏠라티", "truck_van", ("쏠라티", "솔라티", "solati")),
    ("기아 카니발", "truck_van", ("카니발", "carnival")),
    ("기아 타스만", "truck_van", ("타스만", "tasman")),
    # --- SUV ---
    ("팰리세이드", "suv", ("팰리세이드", "펠리세이드", "palisade")),
    ("싼타페", "suv", ("싼타페", "산타페", "santa fe")),
    ("투싼", "suv", ("투싼", "투산", "tucson")),
    ("코나", "suv", ("코나", "kona")),
    ("베뉴", "suv", ("베뉴", "venue")),
    ("캐스퍼", "suv", ("캐스퍼", "casper")),
    ("쏘렌토", "suv", ("쏘렌토", "소렌토", "sorento")),
    ("스포티지", "suv", ("스포티지", "sportage")),
    ("셀토스", "suv", ("셀토스", "seltos")),
    ("니로", "suv", ("니로", "niro")),
    ("모하비", "suv", ("모하비", "mohave")),
    ("제네시스 GV70", "suv", ("GV70",)),
    ("제네시스 GV80", "suv", ("GV80",)),
    ("벤츠 G클래스", "suv", ("G바겐", "지바겐", "겔렌바겐", "G클래스", "지클래스", "G-Wagen", "G-Wagon", "G-Class")),
    ("벤츠 GL 시리즈", "suv", ("GLA", "GLB", "GLC", "GLE", "GLS")),
    ("BMW X 시리즈", "suv", ("X1", "X2", "X3", "X4", "X5", "X6", "X7")),
    ("아우디 Q 시리즈", "suv", ("Q3", "Q5", "Q7", "Q8")),
    ("폭스바겐 티구안", "suv", ("티구안", "tiguan")),
    ("폭스바겐 투아렉", "suv", ("투아렉", "touareg")),
    ("레인지로버", "suv", ("레인지로버", "range rover")),
    ("랜드로버 디펜더", "suv", ("디펜더", "defender")),
    ("지프 랭글러", "suv", ("랭글러", "wrangler")),
    ("포드 익스플로러", "suv", ("익스플로러", "explorer")),
    ("토요타 RAV4", "suv", ("라브4", "RAV4")),
    ("볼보 XC 시리즈", "suv", ("XC40", "XC60", "XC90")),
    ("포르쉐 카이엔", "suv", ("카이엔", "cayenne")),
    ("포르쉐 마칸", "suv", ("마칸", "macan")),
    ("르노 QM6", "suv", ("QM6",)),
    ("KGM 토레스", "suv", ("토레스", "torres")),
    ("KGM 티볼리", "suv", ("티볼리", "tivoli")),
    ("KGM 코란도", "suv", ("코란도", "korando")),
    ("렉스턴", "suv", ("렉스턴", "rexton")),
    # --- Passenger (sedan / hatch / coupe) ---
    ("쏘나타", "passenger", ("쏘나타", "소나타", "sonata")),
    ("아반떼", "passenger", ("아반떼", "엘란트라", "avante", "elantra")),
    ("그랜저", "passenger", ("그랜저", "grandeur")),
    ("현대 i30", "passenger", ("i30",)),
    ("기아 K 시리즈", "passenger", ("K3", "K5", "K7", "K8", "K9")),
    ("기아 스팅어", "passenger", ("스팅어", "stinger")),
    ("제네시스 G70", "passenger", ("G70",)),
    ("제네시스 G80", "passenger", ("G80",)),
    ("제네시스 G90", "passenger", ("G90",)),
    ("벤츠 E클래스", "passenger", ("E클래스", "이클래스", "E-Class")),
    ("벤츠 S클래스", "passenger", ("S클래스", "S-Class")),
    ("벤츠 C클래스", "passenger", ("C클래스", "C-Class")),
    ("벤츠 A클래스", "passenger", ("A클래스", "A-Class")),
    ("벤츠 CLA/CLS", "passenger", ("CLA", "CLS")),
    ("BMW 시리즈", "passenger", ("3 시리즈", "5 시리즈", "7 시리즈")),
    ("아우디 A 시리즈", "passenger", ("A4", "A6", "A8")),
    ("토요타 캠리", "passenger", ("캠리", "camry")),
    ("토요타 프리우스", "passenger", ("프리우스", "prius")),
    ("혼다 어코드", "passenger", ("어코드", "accord")),
    ("혼다 시빅", "passenger", ("시빅", "civic")),
    ("쉐보레 말리부", "passenger", ("말리부", "malibu")),
    ("폭스바겐 파사트", "passenger", ("파사트", "passat")),
    ("르노 SM 시리즈", "passenger", ("SM5", "SM6", "SM7")),
)

_COMPILED: tuple[tuple[str, str, re.Pattern[str]], ...] = tuple(
    (
        model,
        category,
        re.compile("|".join(_alias_pattern(alias) for alias in aliases), re.IGNORECASE),
    )
    for model, category, aliases in _MODEL_ENTRIES
)


def _vehicle_query_for_match(model: str, matched_text: str, text: str, match_end: int) -> str:
    matched_text = re.sub(r"\s+", " ", matched_text or "").strip()
    if not matched_text:
        return model
    maker = model.split(" ", 1)[0] if " " in model else ""
    if "시리즈" in model or "/" in model:
        query = matched_text
        trim_match = re.match(
            r"\s*([A-Za-z]?\d{3}[A-Za-z]?)(?=\s|에|은|는|이|가|도|로|으로|,|\.|\?|!|$)",
            text[match_end:],
        )
        if trim_match and trim_match.group(1).lower() not in query.lower():
            query = f"{query} {trim_match.group(1)}"
        if model.startswith("BMW ") and maker and not re.search(
            rf"(?<![A-Za-z0-9]){re.escape(maker)}(?![A-Za-z0-9])",
            query,
            re.IGNORECASE,
        ):
            return f"{maker} {query}"
        return query
    return model


def match_vehicle_model_category(text: str) -> VehicleModelMatch | None:
    """Return the first cataloged vehicle model mentioned in ``text``, or None."""
    if not text:
        return None
    for model, category, pattern in _COMPILED:
        match = pattern.search(text)
        if match:
            matched_text = match.group(0)
            return VehicleModelMatch(
                model=model,
                category=category,
                masked_text=pattern.sub(" ", text),
                matched_text=matched_text,
                vehicle_query=_vehicle_query_for_match(model, matched_text, text, match.end()),
            )
    return None
