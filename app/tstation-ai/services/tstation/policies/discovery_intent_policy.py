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
_EXTERNAL_PRICE_COMPARE_ANCHOR_RE = re.compile(
    r"다나와|구글|google|네이버(?:\s*쇼핑)?|naver(?:\s*shopping)?|쇼핑\s*검색|쇼핑몰|온라인\s*몰|온라인몰|"
    r"외부\s*(?:몰|사이트|채널)|오픈\s*마켓|오픈마켓|가격\s*비교\s*(?:사이트|앱|플랫폼)?|가격비교|"
    r"포털|검색\s*엔진|검색엔진|쿠팡|coupang|11\s*번가|십일번가|옥션|auction|g\s*마켓|지마켓|gmarket|"
    r"롯데\s*온|롯데온|ssg|쓱|카카오\s*쇼핑|카카오쇼핑|위메프|티몬",
    re.IGNORECASE,
)
_EXTERNAL_PRICE_COMPARE_REQUEST_RE = re.compile(
    r"최저\s*가|최저\s*가격|가격\s*비교|비교\s*가격|어디(?:가|서)?\s*(?:제일|가장)?\s*(?:싸|저렴)|"
    r"(?:싼|저렴한)\s*(?:곳|데|몰|사이트|채널)|외부\s*(?:가격|최저가)|검색(?:해|해서)?\s*(?:줘|봐|찾)",
    re.IGNORECASE,
)
_VALUE_RECOMMENDATION_RE = re.compile(r"가성비|합리적|가격\s*대비|value", re.IGNORECASE)
_NOISE_LABEL_RE = re.compile(r"소음\s*(?:등급|라벨)|저소음\s*등급|소음도|데시벨|dB", re.IGNORECASE)
_QUIET_RECOMMENDATION_RE = re.compile(r"저소음|정숙|조용|소음|진동", re.IGNORECASE)
_EV_RECOMMENDATION_RE = re.compile(
    r"전기차|전기차용|electric|테슬라|모델\s*Y|모델Y|(?<![A-Za-z])EV(?![A-Za-z])",
    re.IGNORECASE,
)
_SUV_RECOMMENDATION_RE = re.compile(r"SUV|스포츠\s*유틸리티", re.IGNORECASE)
_PASSENGER_RECOMMENDATION_RE = re.compile(r"승용차|세단|SEDAN|스포츠카", re.IGNORECASE)
_TRUCK_VAN_RECOMMENDATION_RE = re.compile(r"경트럭|화물차|카고트럭|덤프트럭|트럭|밴|승합차", re.IGNORECASE)
_SOUND_ABSORBER_RE = re.compile(r"흡음재|흡음|sound\s*absorber|소음\s*저감", re.IGNORECASE)
_SAFE_SERVICE_RE = re.compile(r"안심\s*(?:서비스|플러스)|안심서비스|안심플러스", re.IGNORECASE)
_MILEAGE_ATTRIBUTE_RE = re.compile(r"오래\s*(?:타|탈)|수명|내구|마일리지\s*(?:좋|높|긴)|long", re.IGNORECASE)
_MILEAGE_PRODUCT_RE = re.compile(r"마일리지\s*(?:타이어|플러스|plus|\d)", re.IGNORECASE)
_LATEST_RE = re.compile(r"최신|신상|신제품|최근(?:에)?\s*(?:출시|나온)|새로\s*나온|등록일", re.IGNORECASE)
_CONCEPT_RE = re.compile(r"뭐야|무슨\s*뜻|의미|차이|설명", re.IGNORECASE)
_BUY_RE = re.compile(r"구매|살래|주문|장바구니|결제", re.IGNORECASE)
_STOCK_OR_BOOKING_RE = re.compile(r"재고|오늘\s*장착|장착\s*가능|예약|매장|근처|주변", re.IGNORECASE)
_SIMILAR_PRICE_RE = re.compile(r"비슷한\s*가격|가격대|동급\s*가격", re.IGNORECASE)
_QUANTITY_OPTION_RE = re.compile(r"(\d{1,2})\s*(?:개|본)")
_QUANTITY_BENEFIT_RE = re.compile(r"할인|혜택|가격|금액|최종가|저렴|싼|싸|쿠폰", re.IGNORECASE)
_QUANTITY_COMPARE_RE = re.compile(r"비교|중에|살까|고민|더|차이|낫|유리|얼마나", re.IGNORECASE)
_GRADE_COMPARE_RE = re.compile(r"프리미엄|등급|상위|하위|급", re.IGNORECASE)
_COMPARE_RE = re.compile(r"비교|보다|중에|가장|제일|맞지|아냐", re.IGNORECASE)
_RECOMMEND_RE = re.compile(r"추천|찾|골라|보여|알려", re.IGNORECASE)
_BEST_SELLER_RE = re.compile(
    r"인기|베스트\s*셀러|베스트|잘\s*팔리|많이\s*팔린|많이\s*(?:사는|구매한|산)|"
    r"(?:젤|제일|가장)\s*많이\s*(?:사는|구매한|산|팔린)|잘\s*나가|"
    r"최다\s*(?:판매|구매)|판매\s*(?:순위|랭킹|량)|구매\s*(?:순위|랭킹)",
    re.IGNORECASE,
)
_BEST_SELLER_AGGREGATE_RE = re.compile(
    r"베스트\s*셀러|"
    r"(?=.*(?:타이어|상품))"
    r"(?=.*(?:베스트|인기|잘\s*팔리|많이\s*(?:사는|구매한|산|팔린)|"
    r"(?:젤|제일|가장)\s*많이\s*(?:사는|구매한|산|팔린)|잘\s*나가|"
    r"최다\s*(?:판매|구매)|판매\s*(?:순위|랭킹|량)|구매\s*(?:순위|랭킹)))",
    re.IGNORECASE,
)
_DEMOGRAPHIC_ATTRIBUTE_RE = re.compile(
    r"10대|20대|30대|40대|50대|60대|연령대|성별|남성|여성|남자|여자",
    re.IGNORECASE,
)
_DEMOGRAPHIC_PREFERENCE_RE = re.compile(r"선호|좋아하는|많이\s*사는|인기|추천", re.IGNORECASE)
_DEFAULT_TIRE_SHOPPING_RE = re.compile(
    r"(?:t\s*['’]?\s*bot\s*과\s*)?타이어\s*쇼핑\s*하기",
    re.IGNORECASE,
)
_DEFAULT_BENEFIT_RE = re.compile(
    r"지금\s*받을\s*수\s*있는\s*혜택|현재\s*받을\s*수\s*있는\s*혜택|"
    r"진행\s*중인\s*(?:이벤트|행사|혜택)|이벤트\s*/\s*기획전|이벤트랑\s*기획전|"
    r"이벤트(?:와|과|하고)\s*기획전|기획전(?:와|과|하고)\s*이벤트|"
    r"이벤트\s*(?:목록|리스트|검색|조회|보여|알려)",
    re.IGNORECASE,
)
_DEAL_LIST_RE = re.compile(
    r"진행\s*중인\s*기획전|기획전\s*(?:목록|리스트|검색|조회|보여|알려|내용)?",
    re.IGNORECASE,
)
_BEST_SELLER_DAY_RE = re.compile(r"오늘|금일|하루", re.IGNORECASE)
_BEST_SELLER_WEEK_RE = re.compile(r"이번\s*주|금주|이번주|주간", re.IGNORECASE)
_BEST_SELLER_MONTH_RE = re.compile(r"이번\s*달|이달|월별|월간", re.IGNORECASE)
_ONE_PER_VARIANT_RE = re.compile(r"1\s*개씩|한\s*개씩|한개씩|각각|브랜드별|종류별|each", re.IGNORECASE)
_OCCUPATION_RE = re.compile(r"택시|기사|배달|화물", re.IGNORECASE)
_RESTOCK_RE = re.compile(r"재입고|입고|언제\s*들어|언제\s*오|품절|품절인데|다시\s*들어", re.IGNORECASE)
_PRODUCT_ATTRIBUTE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("noise", _NOISE_LABEL_RE),
    ("fuel_efficiency", re.compile(r"연비|회전\s*저항|rr\b", re.IGNORECASE)),
    ("wet", re.compile(r"빗길|젖은\s*노면|젖은노면|wet|제동\s*등급", re.IGNORECASE)),
    ("price_grade", re.compile(r"상품\s*등급|가격\s*등급|프리미엄|스탠다드|이코노미", re.IGNORECASE)),
    ("price", re.compile(r"가격\s*비교|가격\s*차이|더\s*싸|더\s*비싸|가격은\s*얼마|얼마나\s*저렴", re.IGNORECASE)),
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

_PRODUCT_ALIASES: tuple[tuple[str, str, str], ...] = (
    ("ventus air s", "Ventus air S", "HK"),
    ("벤투스 air s", "Ventus air S", "HK"),
    ("벤투스 에어 s", "Ventus air S", "HK"),
    ("ventus s2 as", "Ventus S2 AS", "HK"),
    ("벤투스 s2 as", "Ventus S2 AS", "HK"),
    ("dynapro hpx", "Dynapro HPX", "HK"),
    ("다이나프로 hpx", "Dynapro HPX", "HK"),
    ("dynapro hp3", "Dynapro HP3", "HK"),
    ("다이나프로 hp3", "Dynapro HP3", "HK"),
    ("kinergy ex", "Kinergy EX", "HK"),
    ("키너지 ex", "Kinergy EX", "HK"),
    ("ion evo as", "iON evo AS", "HK"),
    ("아이온 evo as", "iON evo AS", "HK"),
    ("아이온 에보 as", "iON evo AS", "HK"),
    ("ion evo", "iON evo", "HK"),
    ("아이온 evo", "iON evo", "HK"),
    ("아이온 에보", "iON evo", "HK"),
    ("optimo", "Optimo", "HK"),
    ("옵티모", "Optimo", "HK"),
    ("미쉐린 cc2", "Michelin CC2", "MC"),
    ("michelin cc2", "Michelin CC2", "MC"),
    ("마일리지 플러스 2", "Mileage Plus 2", "HK"),
    ("마일리지 플러스2", "Mileage Plus 2", "HK"),
    ("마일리지 플러스 3", "Mileage Plus 3", "HK"),
    ("마일리지 플러스3", "Mileage Plus 3", "HK"),
    ("마일리지 타이어", "Mileage Plus", "HK"),
    ("s fit as", "S FIT AS", "LF"),
    ("s fit", "S FIT", "LF"),
    ("에스핏", "S FIT", "LF"),
    ("g fit as", "G FIT AS", "LF"),
    ("g fit", "G FIT", "LF"),
    ("지핏", "G FIT", "LF"),
    ("i*cept", "i*cept", "HK"),
    ("icept", "i*cept", "HK"),
    ("아이셉트", "아이셉트", "HK"),
    ("4s2", "4S2", "HK"),
    ("dws06", "DWS06", "CT"),
    ("cc7", "CC7", "CT"),
    ("ps4s", "PS4S", "MC"),
    ("ps as 4", "PS AS 4", "MC"),
    ("psas4", "PS AS 4", "MC"),
    ("cup2", "CUP2", "MC"),
    ("cup 2", "CUP2", "MC"),
    ("p7", "P7", "PI"),
    ("세레니티 플러스", "세레니티 플러스", "BS"),
    ("serenity plus", "세레니티 플러스", "BS"),
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
    for needle, display_name, _brand_cd in _PRODUCT_ALIASES:
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


def extract_product_brand_code(text: str) -> str | None:
    normalized = (text or "").casefold()
    for needle, _display_name, brand_cd in _PRODUCT_ALIASES:
        if needle.casefold() in normalized:
            return brand_cd
    return None


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
        season_variants.append({"rcmd_type": "all_weather", "season_nm": "올웨더", "label": "올웨더"})
    if _ALL_SEASON_RE.search(text or ""):
        season_variants.append({"rcmd_type": "all_weather", "season_nm": "사계절", "label": "사계절"})
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


def is_best_seller_request(text: str, *, include_demographic_preference: bool = True) -> bool:
    """Return true for aggregate popularity/sales-ranking requests.

    Keep this helper as the single policy source for best-seller routing so the
    deterministic runtime path and Discovery intent policy do not drift.
    """
    text = text or ""
    if _BEST_SELLER_RE.search(text) and _BEST_SELLER_AGGREGATE_RE.search(text):
        return True
    if not include_demographic_preference:
        return False
    return bool(_DEMOGRAPHIC_ATTRIBUTE_RE.search(text) and _DEMOGRAPHIC_PREFERENCE_RE.search(text))


def best_seller_period_from_text(text: str) -> str | None:
    """Map best-seller wording to BE period values.

    The welcome-screen "지금 가장 인기 있는 타이어는?" button means a current
    popularity ranking, not a generic recommendation. Use the broadest recent
    ranking window the BE supports unless the user names a narrower period.
    """
    text = text or ""
    if not is_best_seller_request(text):
        return None
    if _BEST_SELLER_DAY_RE.search(text):
        return "day"
    if _BEST_SELLER_WEEK_RE.search(text):
        return "week"
    if _BEST_SELLER_MONTH_RE.search(text):
        return "month"
    return "3months"


def is_default_tire_shopping_request(text: str) -> bool:
    """Welcome CTA for starting the normal tire recommendation flow."""
    return bool(_DEFAULT_TIRE_SHOPPING_RE.search(text or ""))


def is_default_benefit_request(text: str) -> bool:
    """Welcome CTA for active event/deal benefits, not owned coupons."""
    return bool(_DEFAULT_BENEFIT_RE.search(text or ""))


def is_deal_list_request(text: str) -> bool:
    """Deal-only listing request. Event listing intentionally returns both events and deals."""
    return bool(_DEAL_LIST_RE.search(text or "")) and not is_default_benefit_request(text)


def extract_quantity_options(text: str) -> tuple[int, ...]:
    quantities: list[int] = []
    for match in _QUANTITY_OPTION_RE.finditer(text or ""):
        try:
            quantity = int(match.group(1))
        except ValueError:
            continue
        if quantity > 0 and quantity not in quantities:
            quantities.append(quantity)
    return tuple(sorted(quantities))


def is_quantity_benefit_comparison_request(text: str) -> bool:
    quantity_options = extract_quantity_options(text)
    return (
        len(quantity_options) >= 2
        and bool(_QUANTITY_BENEFIT_RE.search(text or ""))
        and bool(_QUANTITY_COMPARE_RE.search(text or ""))
    )


def is_external_price_comparison_request(
    text: str,
    *,
    known_slots: dict[str, Any] | None = None,
) -> bool:
    """External-mall price lookup intent anchored by a marketplace/search site mention.

    The external anchor is required so ordinary "최저가 타이어 추천" and
    "할인가 얼마야" flows remain internal T'Station price/search requests.
    """
    text = text or ""
    slots = known_slots or {}
    has_product_or_size = bool(
        normalize_tire_size(text)
        or extract_product_names(text)
        or slots.get("tire_size")
        or slots.get("product_name")
        or slots.get("goods_no")
    )
    return (
        has_product_or_size
        and bool(_EXTERNAL_PRICE_COMPARE_ANCHOR_RE.search(text))
        and bool(_EXTERNAL_PRICE_COMPARE_REQUEST_RE.search(text))
    )


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
    brand_cd = brand_codes[0] if brand_codes else extract_product_brand_code(text)
    quantity_options = extract_quantity_options(text)

    entities: dict[str, Any] = {
        "product_names": products,
        "tire_size": tire_size,
        "explicit_tire_size": explicit_tire_size,
        "purchase_intent": bool(_BUY_RE.search(text)),
        "attribute_metrics": attribute_metrics,
    }
    if quantity_options:
        entities["quantity_options"] = quantity_options
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
    if _QUIET_RECOMMENDATION_RE.search(text):
        entities["quiet_focus"] = True
    if _EV_RECOMMENDATION_RE.search(text):
        entities["vehicle_category"] = "ev"
    elif _SUV_RECOMMENDATION_RE.search(text):
        entities["vehicle_category"] = "suv"
    elif _TRUCK_VAN_RECOMMENDATION_RE.search(text):
        entities["vehicle_category"] = "truck_van"
    elif _PASSENGER_RECOMMENDATION_RE.search(text):
        entities["vehicle_category"] = "passenger"
    if "noise" in attribute_metrics:
        entities["label_metric"] = "noise"
    if _SOUND_ABSORBER_RE.search(text):
        entities["technology"] = "sound_absorber"
        entities["rcmd_type"] = "sound_absorber"
    if _SAFE_SERVICE_RE.search(text):
        entities["service_program"] = "safe_service"
        entities["rcmd_type"] = "safe_kids"
    if _LOWEST_PRICE_RE.search(text):
        entities["price_goal"] = "lowest"
    if _VALUE_RECOMMENDATION_RE.search(text):
        entities["value_focus"] = True
    if _SIMILAR_PRICE_RE.search(text):
        entities["price_goal"] = "similar_range"
    if is_external_price_comparison_request(text, known_slots=slots):
        entities["external_price_comparison"] = True
    best_seller_period = best_seller_period_from_text(text)
    if best_seller_period:
        entities["best_seller_period"] = best_seller_period
    if is_default_tire_shopping_request(text):
        entities["default_tire_shopping"] = True
    if is_default_benefit_request(text):
        entities["default_benefit"] = True
    elif is_deal_list_request(text):
        entities["deal_list_only"] = True

    concept = bool(_CONCEPT_RE.search(text))
    standalone_attribute_metrics = tuple(
        metric for metric in attribute_metrics if metric not in ("season", "car_type")
    )
    if entities.get("external_price_comparison"):
        intent = "product_search"
        sub_intent = "external_price_comparison_request"
    elif entities.get("default_benefit"):
        intent = "product_search"
        sub_intent = "benefit_event_deal_list"
    elif entities.get("deal_list_only"):
        intent = "product_search"
        sub_intent = "benefit_deal_list"
    elif is_quantity_benefit_comparison_request(text):
        intent = "product_comparison"
        sub_intent = "quantity_benefit_comparison"
        entities["compare_metric"] = "discount"
    elif best_seller_period:
        intent = "product_search"
        sub_intent = "best_seller_search"
    elif entities.get("default_tire_shopping"):
        intent = "product_recommendation"
        sub_intent = "general_recommendation"
    elif _MILEAGE_PRODUCT_RE.search(text):
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
    elif (
        _SOUND_ABSORBER_RE.search(text)
        or _SAFE_SERVICE_RE.search(text)
        or _PERFORMANCE_RE.search(text)
        or _LOWEST_PRICE_RE.search(text)
    ):
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
    elif products:
        intent = "product_search"
        sub_intent = "product_name_search"
    else:
        intent = "product_recommendation"
        sub_intent = "general_recommendation"

    missing_slots: tuple[str, ...] = ()
    if intent == "product_recommendation" and not tire_size and entities.get("price_goal") == "lowest":
        missing_slots = ("tire_size",)
    elif sub_intent == "quantity_benefit_comparison" and not tire_size and not slots.get("goods_no"):
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
    if frame.sub_intent == "external_price_comparison_request":
        product_names = entities.get("product_names") or ()
        args = {"limit": 5, "sort_by": "price_asc"}
        if product_names:
            args["keyword"] = product_names[0]
        if entities.get("tire_size"):
            args["size"] = entities["tire_size"]
        if entities.get("brand_cd"):
            args["brand_cd"] = entities["brand_cd"]
        return ToolPlan(
            allowed_tools=("search_product_tool",),
            preferred_tool="search_product_tool",
            tool_args_patch=args,
            forbidden_tools=(
                "get_product_description_tool",
                "get_products_recommendations_tool",
                "product_attribute_lookup",
                "external_price_scraping",
            ),
        )
    if frame.sub_intent == "benefit_event_deal_list":
        return ToolPlan(
            allowed_tools=("get_events_tool", "get_deals_tool"),
            preferred_tool="get_events_tool",
            tool_args_patch={"lang_cd": "ko"},
            forbidden_tools=("get_my_coupons_tool",),
        )
    if frame.sub_intent == "benefit_deal_list":
        return ToolPlan(
            allowed_tools=("get_deals_tool",),
            preferred_tool="get_deals_tool",
            tool_args_patch={},
            forbidden_tools=("get_events_tool", "get_my_coupons_tool"),
        )
    if frame.sub_intent == "best_seller_search":
        args = {"period": entities.get("best_seller_period") or "3months", "limit": 5}
        return ToolPlan(
            allowed_tools=("get_best_selling_products_tool",),
            preferred_tool="get_best_selling_products_tool",
            tool_args_patch=args,
            forbidden_tools=("get_products_recommendations_tool",),
        )
    if frame.intent == "product_search":
        keyword = entities.get("product_keyword") or (entities.get("product_names") or ("",))[0]
        args = {"keyword": keyword}
        if entities.get("tire_size"):
            args["size"] = entities["tire_size"]
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
        args: dict[str, Any] = {}
        if frame.sub_intent == "quantity_benefit_comparison":
            product_names = entities.get("product_names") or ()
            if product_names:
                args["keyword"] = product_names[0]
            if entities.get("tire_size"):
                args["size"] = entities["tire_size"]
            if entities.get("brand_cd"):
                args["brand_cd"] = entities["brand_cd"]
        return ToolPlan(
            allowed_tools=("search_product_tool", "get_products_recommendations_tool"),
            preferred_tool="search_product_tool",
            tool_args_patch=args,
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
    if entities.get("service_program") == "safe_service":
        args = {"rcmd_type": "safe_kids", "brand_cd": entities.get("brand_cd") or "HK"}
        if entities.get("tire_size"):
            args["tire_size"] = entities["tire_size"]
        return ToolPlan(
            allowed_tools=("get_products_recommendations_tool",),
            preferred_tool="get_products_recommendations_tool",
            tool_args_patch=args,
            forbidden_tools=("generic_unsized_recommendation",),
        )
    args = {}
    if entities.get("vehicle_category"):
        args["vehicle_type"] = entities["vehicle_category"]
    if entities.get("quiet_focus"):
        args["rcmd_type"] = "low_vibration"
    elif entities.get("value_focus"):
        args["rcmd_type"] = "value"
    elif entities.get("recommendation_metric") == "fuel_efficiency":
        args["rcmd_type"] = "fuel_efficiency"
    elif entities.get("performance") == "performance":
        args["rcmd_type"] = "performance"
    if entities.get("season") == "winter":
        if args.get("rcmd_type"):
            args["season_nm"] = "겨울"
        else:
            args.update({"rcmd_type": "snow", "season_nm": "겨울"})
    elif entities.get("season") == "all_weather":
        if args.get("rcmd_type"):
            args["season_nm"] = "올웨더"
        else:
            args.update({"rcmd_type": "all_weather", "season_nm": "올웨더"})
    elif entities.get("season") == "all_season":
        if args.get("rcmd_type"):
            args["season_nm"] = "사계절"
        else:
            args.update({"rcmd_type": "all_weather", "season_nm": "사계절"})
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
