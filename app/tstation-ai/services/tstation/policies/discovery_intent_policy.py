"""Deterministic intent policy for Discovery product flows."""

from __future__ import annotations

import re
from typing import Any

from services.tstation.policies.intent_frame import IntentFrame, PolicyDomain
from services.tstation.policies.response_decision import ToolPlan


_SIZE_COMPACT_RE = re.compile(r"\b(\d{3})\s*/?\s*(\d{2})\s*R?\s*(\d{2})\b", re.IGNORECASE)
_SUMMER_RE = re.compile(r"여름|썸머|summer", re.IGNORECASE)
_WINTER_RE = re.compile(r"윈터|겨울|스노우|snow|winter", re.IGNORECASE)
_ALL_WEATHER_RE = re.compile(r"올웨더|all\s*weather", re.IGNORECASE)
_ALL_SEASON_RE = re.compile(r"사계절|올시즌|all\s*season", re.IGNORECASE)
_PERFORMANCE_RE = re.compile(r"퍼포먼스|고성능|스포츠|performance", re.IGNORECASE)
_LOWEST_PRICE_RE = re.compile(r"가장\s*저렴|제일\s*저렴|최저가|싼\s*거|저렴한", re.IGNORECASE)
_NOISE_LABEL_RE = re.compile(r"소음\s*(?:등급|라벨)|저소음\s*등급|소음도|데시벨|dB", re.IGNORECASE)
_SOUND_ABSORBER_RE = re.compile(r"흡음재|흡음|sound\s*absorber|소음\s*저감", re.IGNORECASE)
_MILEAGE_ATTRIBUTE_RE = re.compile(r"오래\s*(?:타|탈)|수명|내구|마일리지\s*(?:좋|높|긴)|long", re.IGNORECASE)
_MILEAGE_PRODUCT_RE = re.compile(r"마일리지\s*(?:타이어|플러스|plus|\d)", re.IGNORECASE)
_LATEST_RE = re.compile(r"최신|신제품|최근\s*출시|새로\s*나온|등록일", re.IGNORECASE)
_CONCEPT_RE = re.compile(r"뭐야|무슨\s*뜻|의미|차이|설명", re.IGNORECASE)
_BUY_RE = re.compile(r"구매|살래|주문|장바구니|결제", re.IGNORECASE)
_STOCK_OR_BOOKING_RE = re.compile(r"재고|오늘\s*장착|장착\s*가능|예약|매장|근처|주변", re.IGNORECASE)
_SIMILAR_PRICE_RE = re.compile(r"비슷한\s*가격|가격대|동급\s*가격", re.IGNORECASE)
_GRADE_COMPARE_RE = re.compile(r"프리미엄|등급|상위|하위|급", re.IGNORECASE)
_COMPARE_RE = re.compile(r"비교|보다|중에|가장|제일|맞지|아냐", re.IGNORECASE)
_RECOMMEND_RE = re.compile(r"추천|찾|골라|보여|알려", re.IGNORECASE)
_ONE_PER_VARIANT_RE = re.compile(r"1\s*개씩|한\s*개씩|한개씩|각각|브랜드별|종류별|each", re.IGNORECASE)
_OCCUPATION_RE = re.compile(r"택시|기사|배달|화물", re.IGNORECASE)
_RESTOCK_RE = re.compile(r"재입고|입고|언제\s*들어|언제\s*오|품절|품절인데|다시\s*들어", re.IGNORECASE)
_PRODUCT_ATTRIBUTE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("noise", _NOISE_LABEL_RE),
    ("fuel_efficiency", re.compile(r"연비|회전\s*저항|rr\b", re.IGNORECASE)),
    ("wet", re.compile(r"빗길|젖은\s*노면|젖은노면|wet|제동\s*등급", re.IGNORECASE)),
    ("price_grade", re.compile(r"상품\s*등급|가격\s*등급|프리미엄|스탠다드|이코노미", re.IGNORECASE)),
    ("release", re.compile(r"출시|출시일|출시년도|등록일", re.IGNORECASE)),
    ("origin", re.compile(r"원산지|생산국|제조국|어느\s*나라", re.IGNORECASE)),
    ("load", re.compile(r"하중|하중지수|무게", re.IGNORECASE)),
    ("speed", re.compile(r"속도\s*기호|속도|고속", re.IGNORECASE)),
    ("season", re.compile(r"계절|사계절|겨울용|여름용|올웨더|올시즌", re.IGNORECASE)),
    ("car_type", re.compile(r"차종|승용차|suv|전기차용|전기차", re.IGNORECASE)),
)
_RECOMMENDATION_ATTRIBUTE_METRICS: frozenset[str] = frozenset(
    {"fuel_efficiency", "wet", "load", "speed"}
)

_PRODUCT_ALIASES: tuple[tuple[str, str], ...] = (
    ("ventus air s", "Ventus air S"),
    ("벤투스 air s", "Ventus air S"),
    ("벤투스 에어 s", "Ventus air S"),
    ("ventus s2 as", "Ventus S2 AS"),
    ("벤투스 s2 as", "Ventus S2 AS"),
    ("dynapro hpx", "Dynapro HPX"),
    ("다이나프로 hpx", "Dynapro HPX"),
    ("dynapro hp3", "Dynapro HP3"),
    ("다이나프로 hp3", "Dynapro HP3"),
    ("kinergy ex", "Kinergy EX"),
    ("키너지 ex", "Kinergy EX"),
    ("ion evo as", "iON evo AS"),
    ("아이온 evo as", "iON evo AS"),
    ("아이온 에보 as", "iON evo AS"),
    ("ion evo", "iON evo"),
    ("아이온 evo", "iON evo"),
    ("아이온 에보", "iON evo"),
    ("optimo", "Optimo"),
    ("옵티모", "Optimo"),
    ("미쉐린 cc2", "Michelin CC2"),
    ("michelin cc2", "Michelin CC2"),
    ("마일리지 플러스 2", "Mileage Plus 2"),
    ("마일리지 플러스2", "Mileage Plus 2"),
    ("마일리지 플러스 3", "Mileage Plus 3"),
    ("마일리지 플러스3", "Mileage Plus 3"),
    ("마일리지 타이어", "Mileage Plus"),
)
_BRAND_ALIASES: tuple[tuple[str, str], ...] = (
    ("한국타이어", "HK"),
    ("hankook", "HK"),
    ("라우펜", "LF"),
    ("laufenn", "LF"),
    ("미쉐린", "MC"),
    ("michelin", "MC"),
    ("피렐리", "PI"),
    ("pirelli", "PI"),
    ("브리지스톤", "BS"),
    ("bridgestone", "BS"),
    ("콘티넨탈", "CT"),
    ("continental", "CT"),
    ("굿이어", "GY"),
    ("goodyear", "GY"),
)


def normalize_tire_size(text: str) -> str | None:
    match = _SIZE_COMPACT_RE.search(text or "")
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}R{match.group(3)}"


def extract_product_names(text: str) -> tuple[str, ...]:
    normalized = (text or "").casefold()
    products: list[str] = []
    for needle, display_name in _PRODUCT_ALIASES:
        if needle.casefold() in normalized and display_name not in products:
            products.append(display_name)
    return tuple(products)


def extract_brand_codes(text: str) -> tuple[str, ...]:
    normalized = (text or "").casefold()
    matches: list[tuple[int, str]] = []
    seen: set[str] = set()
    for needle, brand_cd in _BRAND_ALIASES:
        idx = normalized.find(needle.casefold())
        if idx < 0 or brand_cd in seen:
            continue
        matches.append((idx, brand_cd))
        seen.add(brand_cd)
    matches.sort(key=lambda item: item[0])
    return tuple(brand_cd for _, brand_cd in matches)


def extract_brand_code(text: str) -> str | None:
    brand_codes = extract_brand_codes(text)
    return brand_codes[0] if brand_codes else None


def extract_product_attribute_metrics(text: str) -> tuple[str, ...]:
    metrics: list[str] = []
    for metric, pattern in _PRODUCT_ATTRIBUTE_PATTERNS:
        if pattern.search(text or "") and metric not in metrics:
            metrics.append(metric)
    return tuple(metrics)


def extract_variant_constraints(text: str) -> tuple[dict[str, Any], ...]:
    variants: list[dict[str, Any]] = []
    brand_codes = extract_brand_codes(text)
    if len(brand_codes) >= 2:
        variants.extend({"brand_cd": brand_cd} for brand_cd in brand_codes)
        return tuple(variants)

    season_variants: list[dict[str, Any]] = []
    if _SUMMER_RE.search(text or ""):
        season_variants.append({"season_nm": "여름", "label": "여름용"})
    if _WINTER_RE.search(text or ""):
        season_variants.append({"rcmd_type": "snow", "season_nm": "겨울", "label": "겨울용"})
    if _ALL_WEATHER_RE.search(text or ""):
        season_variants.append({"rcmd_type": "all_weather", "label": "올웨더"})
    if _ALL_SEASON_RE.search(text or ""):
        season_variants.append({"rcmd_type": "all_weather", "label": "사계절"})
    deduped: list[dict[str, Any]] = []
    seen_keys: set[tuple[tuple[str, Any], ...]] = set()
    for variant in season_variants:
        key = tuple(sorted(variant.items()))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(variant)
    if len(deduped) >= 2 and _RECOMMEND_RE.search(text or "") and _ONE_PER_VARIANT_RE.search(text or ""):
        return tuple(deduped)
    return ()


def build_discovery_intent_frame(
    last_user_text: str,
    *,
    known_slots: dict[str, Any] | None = None,
) -> IntentFrame:
    text = last_user_text or ""
    slots = dict(known_slots or {})
    explicit_tire_size = normalize_tire_size(text)
    tire_size = explicit_tire_size or slots.get("tire_size")
    products = extract_product_names(text)
    attribute_metrics = extract_product_attribute_metrics(text)
    brand_codes = extract_brand_codes(text)
    variant_constraints = extract_variant_constraints(text)
    brand_cd = brand_codes[0] if brand_codes else None

    entities: dict[str, Any] = {
        "product_names": products,
        "tire_size": tire_size,
        "explicit_tire_size": explicit_tire_size,
        "purchase_intent": bool(_BUY_RE.search(text)),
        "attribute_metrics": attribute_metrics,
    }
    if brand_cd:
        entities["brand_cd"] = brand_cd
    if brand_codes:
        entities["brand_codes"] = brand_codes
    if variant_constraints:
        entities["variant_constraints"] = variant_constraints
    if _SUMMER_RE.search(text):
        entities["season"] = "summer"
    elif _WINTER_RE.search(text):
        entities["season"] = "winter"
    elif _ALL_WEATHER_RE.search(text):
        entities["season"] = "all_weather"
    elif _ALL_SEASON_RE.search(text):
        entities["season"] = "all_season"

    if _PERFORMANCE_RE.search(text):
        entities["performance"] = "performance"
    if "noise" in attribute_metrics:
        entities["label_metric"] = "noise"
    if _SOUND_ABSORBER_RE.search(text):
        entities["technology"] = "sound_absorber"
        entities["rcmd_type"] = "sound_absorber"
    if _LOWEST_PRICE_RE.search(text):
        entities["price_goal"] = "lowest"
    if _SIMILAR_PRICE_RE.search(text):
        entities["price_goal"] = "similar_range"

    concept = bool(_CONCEPT_RE.search(text))
    standalone_attribute_metrics = tuple(
        metric for metric in attribute_metrics if metric not in ("season", "car_type")
    )
    if _MILEAGE_PRODUCT_RE.search(text):
        entities["product_keyword"] = "마일리지"
        if _OCCUPATION_RE.search(text):
            entities["guardrail"] = "occupation_neutral"
        intent = "product_search"
        sub_intent = "product_name_search"
    elif _GRADE_COMPARE_RE.search(text) and len(products) >= 2:
        intent = "product_comparison"
        sub_intent = "grade_compare"
        entities["compare_metric"] = "grade"
    elif _LATEST_RE.search(text) and len(products) >= 2:
        intent = "product_comparison"
        sub_intent = "latest_compare"
        entities["compare_metric"] = "release"
    elif _MILEAGE_ATTRIBUTE_RE.search(text) and (_COMPARE_RE.search(text) or len(products) >= 2):
        intent = "product_comparison"
        sub_intent = "mileage_compare"
        entities["compare_metric"] = "mileage"
    elif attribute_metrics and len(products) >= 2 and _COMPARE_RE.search(text):
        intent = "product_comparison"
        sub_intent = "attribute_compare"
        entities["compare_metric"] = attribute_metrics[0]
    elif _OCCUPATION_RE.search(text) and _MILEAGE_ATTRIBUTE_RE.search(text):
        intent = "product_description"
        sub_intent = "mileage_bias_guardrail"
        entities["compare_metric"] = "mileage"
        entities["guardrail"] = "occupation_neutral"
    elif concept and _SOUND_ABSORBER_RE.search(text) and entities["purchase_intent"]:
        intent = "product_recommendation"
        sub_intent = "technology_explain_then_recommend"
    elif variant_constraints and len(variant_constraints) >= 2:
        intent = "product_recommendation"
        sub_intent = "general_recommendation"
    elif concept and _WINTER_RE.search(text) and _ALL_SEASON_RE.search(text):
        intent = "product_description"
        sub_intent = "season_concept_compare"
    elif attribute_metrics and products:
        intent = "product_description"
        sub_intent = "product_attribute_lookup"
    elif standalone_attribute_metrics and _RECOMMEND_RE.search(text) and any(
        metric in _RECOMMENDATION_ATTRIBUTE_METRICS for metric in standalone_attribute_metrics
    ):
        intent = "product_recommendation"
        sub_intent = "condition_recommendation"
        entities["recommendation_metric"] = next(
            metric for metric in standalone_attribute_metrics if metric in _RECOMMENDATION_ATTRIBUTE_METRICS
        )
    elif standalone_attribute_metrics:
        intent = "product_description"
        sub_intent = "product_attribute_explanation"
    elif _SIMILAR_PRICE_RE.search(text):
        intent = "product_recommendation"
        sub_intent = "similar_price_recommendation"
    elif _SOUND_ABSORBER_RE.search(text) or _PERFORMANCE_RE.search(text) or _LOWEST_PRICE_RE.search(text):
        intent = "product_recommendation"
        sub_intent = "condition_recommendation"
    elif products and concept:
        intent = "product_description"
        sub_intent = "product_detail"
    elif products and _RESTOCK_RE.search(text):
        intent = "product_search"
        sub_intent = "restock_inquiry"
        entities["restock_inquiry"] = True
    elif products and _STOCK_OR_BOOKING_RE.search(text):
        intent = "product_search"
        sub_intent = "product_name_search"
    else:
        intent = "product_recommendation"
        sub_intent = "general_recommendation"

    missing_slots: tuple[str, ...] = ()
    if intent == "product_recommendation" and not tire_size and entities.get("price_goal") == "lowest":
        missing_slots = ("tire_size",)

    return IntentFrame(
        domain=PolicyDomain.DISCOVERY,
        intent=intent,
        sub_intent=sub_intent,
        entities=entities,
        known_slots=slots,
        missing_slots=missing_slots,
        confidence=0.9,
    )


def plan_discovery_tools(frame: IntentFrame) -> ToolPlan:
    entities = frame.entities
    if frame.intent == "product_search":
        keyword = entities.get("product_keyword") or (entities.get("product_names") or ("",))[0]
        args = {"keyword": keyword}
        if entities.get("brand_cd"):
            args["brand_cd"] = entities["brand_cd"]
        return ToolPlan(
            allowed_tools=("search_product_tool",),
            preferred_tool="search_product_tool",
            tool_args_patch=args,
            forbidden_tools=("get_products_recommendations_tool",),
        )
    if frame.sub_intent == "product_attribute_lookup":
        args = {"keyword": (entities.get("product_names") or ("",))[0]}
        if entities.get("brand_cd"):
            args["brand_cd"] = entities["brand_cd"]
        return ToolPlan(
            allowed_tools=("search_product_tool",),
            preferred_tool="search_product_tool",
            tool_args_patch=args,
            forbidden_tools=("get_products_recommendations_tool", "generic_unsized_recommendation"),
        )
    if frame.intent == "product_comparison":
        return ToolPlan(
            allowed_tools=("search_product_tool", "get_products_recommendations_tool"),
            preferred_tool="search_product_tool",
            forbidden_tools=("product_card_first_response",),
        )
    if entities.get("technology") == "sound_absorber":
        args = {"rcmd_type": "sound_absorber"}
        if entities.get("tire_size"):
            args["tire_size"] = entities["tire_size"]
        if entities.get("brand_cd"):
            args["brand_cd"] = entities["brand_cd"]
        return ToolPlan(
            allowed_tools=("get_products_recommendations_tool",),
            preferred_tool="get_products_recommendations_tool",
            tool_args_patch=args,
            forbidden_tools=("generic_noise_recommendation",),
        )
    args = {}
    if entities.get("recommendation_metric") == "fuel_efficiency":
        args["rcmd_type"] = "tstation"
        args["sort_by"] = "fuel_efficiency_desc"
    elif entities.get("performance") == "performance":
        args["rcmd_type"] = "performance"
    if entities.get("season") == "winter":
        args.update({"rcmd_type": "snow", "season_nm": "겨울"})
    elif entities.get("season") == "all_weather":
        args.update({"rcmd_type": "all_weather"})
    elif entities.get("season") == "summer":
        args["season_nm"] = "여름"
    if entities.get("explicit_tire_size") or entities.get("price_goal") != "similar_range":
        if entities.get("tire_size"):
            args["tire_size"] = entities["tire_size"]
    if entities.get("price_goal") == "lowest":
        args["sort_by"] = "price_asc"
    if entities.get("brand_cd"):
        args["brand_cd"] = entities["brand_cd"]
    return ToolPlan(
        allowed_tools=("get_products_recommendations_tool",),
        preferred_tool="get_products_recommendations_tool",
        tool_args_patch=args,
    )
