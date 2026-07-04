"""Deterministic intent policy for Discovery product flows."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Mapping

from services.tstation.policies.intent_frame import IntentFrame, PolicyDomain
from services.tstation.policies.recommendation_scenario_catalog import (
    recommendation_scenario_from_text,
    recommendation_scenario_metadata,
)
from services.tstation.policies.response_decision import ToolPlan
from services.tstation.policies.vehicle_category_catalog import match_vehicle_model_category


def _recommendation_context_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_policy_dict"):
        try:
            return {key: item for key, item in value.to_policy_dict().items() if item not in (None, "")}
        except Exception:
            return {}
    if isinstance(value, Mapping):
        data = {key: item for key, item in value.items() if item not in (None, "")}
        if "recommendation_scenario" not in data and data.get("scenario"):
            data["recommendation_scenario"] = data.get("scenario")
        return data
    return {}


def _recommendation_expected_tool_args(args: Mapping[str, Any]) -> dict[str, Any]:
    tracked_keys = (
        "rcmd_type",
        "vehicle_type",
        "season_nm",
        "tire_size",
        "car_lnc_cd",
        "brand_cd",
        "allow_cross_brand_fill",
        "pfm_nm",
        "prc_grd",
        "sort_by",
        "min_price",
        "max_price",
    )
    return {key: args[key] for key in tracked_keys if args.get(key) not in (None, "")}


def _normalize_vehicle_anchor(value: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", str(value or "")).lower()


def _named_vehicle_anchor_from_pattern(text: str | None, pattern: re.Pattern[str]) -> str | None:
    for match in pattern.finditer(text or ""):
        raw = re.sub(r"\s+", " ", match.group("model") or "").strip(" ._-")
        normalized = _normalize_vehicle_anchor(raw)
        if len(normalized) < 2 or normalized in _MY_NAMED_VEHICLE_STOPWORDS:
            continue
        return raw
    return None


def _named_my_vehicle_anchor(text: str) -> str | None:
    registered_anchor = _named_vehicle_anchor_from_pattern(text, _REGISTERED_NAMED_VEHICLE_RE)
    if registered_anchor:
        return registered_anchor
    if has_registered_vehicle_ownership_signal(text):
        return None
    return _named_vehicle_anchor_from_pattern(text, _MY_NAMED_VEHICLE_RE)


_TIRE_SIZE_PRICE_PARSE_MASK_RE = re.compile(
    r"(?<!\d)(\d{3})\s*/?\s*(\d{2})\s*R?\s*(\d{2})(?=\s*\d{1,3}\s*만원|[^\d]|$)",
    re.IGNORECASE,
)


def _price_range_from_text(text: str) -> dict[str, int]:
    size_masked_text = _TIRE_SIZE_PRICE_PARSE_MASK_RE.sub(" ", text or "")
    normalized = re.sub(r"\s+", "", size_masked_text)
    if not normalized:
        return {}
    match = re.search(r"(?<!\d)(?P<low>\d{1,3})만원(?:대|선)", normalized)
    if match:
        low = int(match.group("low")) * 10_000
        return {"min_price": low, "max_price": low + 99_999}
    match = re.search(
        r"(?<!\d)(?P<low>\d{1,3})만원(?:부터|이상)[~\-]?(?P<high>\d{1,3})?만원?(?:까지|이하)?",
        normalized,
    )
    if match:
        result = {"min_price": int(match.group("low")) * 10_000}
        if match.group("high"):
            result["max_price"] = int(match.group("high")) * 10_000
        return result
    match = re.search(r"(?<!\d)(?P<low>\d{1,3})만원[~\-](?P<high>\d{1,3})만원", normalized)
    if match:
        return {
            "min_price": int(match.group("low")) * 10_000,
            "max_price": int(match.group("high")) * 10_000,
        }
    match = re.search(r"(?<!\d)(?P<price>\d{1,3})만원(?:이하|까지|안쪽|미만)", normalized)
    if match:
        return {"max_price": int(match.group("price")) * 10_000}
    match = re.search(r"(?<!\d)(?P<price>\d{1,3})만원(?:이상|부터)", normalized)
    if match:
        return {"min_price": int(match.group("price")) * 10_000}
    return {}


def _is_general_tire_recommendation_request(text: str) -> bool:
    text = text or ""
    return (
        bool(_GENERAL_TIRE_RECOMMENDATION_ACTION_RE.search(text))
        and bool(_GENERAL_TIRE_PREFERENCE_RE.search(text) or _NON_EV_TIRE_PREFERENCE_RE.search(text))
    )


def has_registered_vehicle_ownership_signal(text: str | None) -> bool:
    return bool(_REGISTERED_VEHICLE_OWNERSHIP_RE.search(text or ""))


def has_registered_vehicle_size_lookup_signal(text: str | None) -> bool:
    value = text or ""
    if _VEHICLE_SIZE_LOOKUP_RE.search(value):
        return True
    if not has_registered_vehicle_ownership_signal(value):
        return False
    return bool(re.search(r"타이어\s*사이즈|타이어\s*규격|규격|사이즈", value, re.IGNORECASE))


def has_registered_vehicle_type_query_signal(text: str | None) -> bool:
    return bool(_REGISTERED_VEHICLE_TYPE_QUERY_RE.search(text or ""))


_SIZE_COMPACT_RE = re.compile(r"\b(\d{3})\s*/?\s*(\d)(\d)(?:\3)?\s*R?\s*(\d{2})\b", re.IGNORECASE)
_SUMMER_RE = re.compile(r"여름|썸머|summer", re.IGNORECASE)
_WINTER_RE = re.compile(r"윈터|겨울|스노우|snow|winter", re.IGNORECASE)
_ALL_WEATHER_RE = re.compile(r"올웨더|all\s*weather", re.IGNORECASE)
_ALL_SEASON_RE = re.compile(r"사계절|올시즌|all\s*season", re.IGNORECASE)
_PERFORMANCE_RE = re.compile(r"퍼포먼스|고성능|스포츠|performance", re.IGNORECASE)
_LOWEST_PRICE_RE = re.compile(r"가장\s*저렴|제일\s*저렴|최저가|싼\s*거|저렴한", re.IGNORECASE)
_MULTI_PRODUCT_DESCRIPTION_RE = re.compile(r"설명|특징|장점|상세|상품\s*정보|정보", re.IGNORECASE)
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
    r"전기차|전기차용|electric|일렉트릭|(?<![A-Za-z])EV(?![A-Za-z])",
    re.IGNORECASE,
)
_GENERAL_TIRE_RECOMMENDATION_ACTION_RE = re.compile(
    r"추천|찾|골라|보여|낄\s*수\s*있는|끼울\s*수\s*있는|장착\s*가능한",
    re.IGNORECASE,
)
_MY_VEHICLE_RECOMMENDATION_RE = re.compile(
    r"(?:내(?:가)?\s*(?:등록(?:한|해\s*둔|해둔|된)?|보유(?:한)?)\s*(?:차|차량)|"
    r"내\s*차|내차|내\s*차량|내차량|등록\s*차량|등록차)"
    r".{0,24}(?:적합|맞는|맞춰|기준|추천|찾|골라)|"
    r"(?:적합|맞는|맞춰|기준).{0,24}(?:내(?:가)?\s*(?:등록(?:한|해\s*둔|해둔|된)?|보유(?:한)?)\s*(?:차|차량)|"
    r"내\s*차|내차|내\s*차량|내차량|등록\s*차량|등록차)",
    re.IGNORECASE,
)
_REGISTERED_VEHICLE_OWNERSHIP_RE = re.compile(
    r"내(?:가)?\s*(?:(?:홈페이지|사이트|티스테이션|계정)에?\s*)?"
    r"(?:등록(?:한|해\s*둔|해둔|된)?|보유(?:한)?)\s*(?:차|차량)|"
    r"내\s*등록\s*(?:차|차량)|"
    r"등록(?:한|해\s*둔|해둔|된)?\s*내\s*(?:차|차량)|"
    r"(?:홈페이지|사이트|티스테이션|계정)에?\s*등록(?:한|해\s*둔|해둔|된)?\s*내\s*(?:차|차량)",
    re.IGNORECASE,
)
_REGISTERED_VEHICLE_TYPE_QUERY_RE = re.compile(
    r"(?:내(?:가)?\s*(?:(?:홈페이지|사이트|티스테이션|계정)에?\s*)?"
    r"(?:등록(?:한|해\s*둔|해둔|된)?|보유(?:한)?)?\s*(?:차종|차량|차)|"
    r"등록(?:한|해\s*둔|해둔|된)?\s*내\s*(?:차종|차량|차)|"
    r"(?:홈페이지|사이트|티스테이션|계정)에?\s*등록(?:한|해\s*둔|해둔|된)?\s*내\s*(?:차종|차량|차))"
    r"(?:이|가)?\s*(?:목록|리스트|보기|보여\s*(?:줘|주세요)?|확인|조회|"
    r"뭐(?:야|니|고|였|지|든지|ㄴ지)?|뭔지|뭔가|"
    r"무슨\s*(?:차|차종|차량)인지|어떤\s*(?:차|차종|차량)인지|알려\s*(?:줘|줄래|주세요|주라)?)",
    re.IGNORECASE,
)
_REGISTERED_NAMED_VEHICLE_RE = re.compile(
    r"(?:내(?:가)?\s*(?:(?:홈페이지|사이트|티스테이션|계정)에?\s*)?"
    r"(?:등록(?:한|해\s*둔|해둔|된)?|보유(?:한)?)\s*(?:차|차량)|"
    r"내\s*등록\s*(?:차|차량)|등록(?:한|해\s*둔|해둔|된)?\s*내\s*(?:차|차량)|등록\s*차량|등록차)"
    r"\s*(?:목록\s*)?중(?:에|에서)?\s*"
    r"(?P<model>[0-9A-Za-z가-힣][0-9A-Za-z가-힣\s._-]{1,24}?)(?="
    r"\s*(?:기준|에|에는|으로|로|타이어|상품|추천|맞|적합|사이즈|규격|$)"
    r")",
    re.IGNORECASE,
)
_MY_NAMED_VEHICLE_RE = re.compile(
    r"(?:내\s*차|내차|내\s*차량|내차량|내)\s*"
    r"(?:중(?:에|에서)?\s*)?"
    r"(?P<model>[0-9A-Za-z가-힣][0-9A-Za-z가-힣\s._-]{1,24}?)(?="
    r"\s*(?:기준|에|에는|으로|로|타이어|상품|추천|맞|적합|$)"
    r")",
    re.IGNORECASE,
)
_MY_NAMED_VEHICLE_STOPWORDS = frozenset({
    "내",
    "내차",
    "차",
    "차량",
    "기준",
    "타이어",
    "상품",
    "추천",
    "등록차",
    "등록차량",
    "등록한차",
    "등록한차량",
    "중",
    "중에",
})
_GENERAL_TIRE_PREFERENCE_RE = re.compile(
    r"일반\s*타이어|일반타이어|승용차?\s*용\s*타이어|승용\s*타이어",
    re.IGNORECASE,
)
_NON_EV_TIRE_PREFERENCE_RE = re.compile(
    r"(?:전기차(?:용|\s*전용)?|electric|(?<![A-Za-z])EV(?![A-Za-z])).{0,20}"
    r"(?:말고|아닌|아니고|빼고|제외)|"
    r"(?:말고|아닌|아니고|빼고|제외).{0,20}"
    r"(?:전기차(?:용|\s*전용)?|electric|(?<![A-Za-z])EV(?![A-Za-z]))",
    re.IGNORECASE,
)
_SUV_RECOMMENDATION_RE = re.compile(r"SUV|스포츠\s*유틸리티", re.IGNORECASE)
_PASSENGER_RECOMMENDATION_RE = re.compile(r"승용차|세단|SEDAN|스포츠카", re.IGNORECASE)
_TRUCK_VAN_RECOMMENDATION_RE = re.compile(r"경트럭|화물차|카고트럭|덤프트럭|트럭|밴|승합차", re.IGNORECASE)
_SOUND_ABSORBER_RE = re.compile(r"흡음재|흡음|sound\s*absorber|소음\s*저감", re.IGNORECASE)
_SAFE_SERVICE_RE = re.compile(r"안심\s*(?:서비스|플러스)|안심서비스|안심플러스", re.IGNORECASE)
_OE_REPLACEMENT_TYPE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("oe", re.compile(r"(?:\bOE\b|순정|출고\s*타이어|출고용|출고때|출고 시)", re.IGNORECASE)),
    ("re", re.compile(r"(?:\bRE\b|교체용|replacement)", re.IGNORECASE)),
)
_OE_PART_NUMBER_REQUEST_RE = re.compile(
    r"(?:\bOE\b|순정|출고\s*타이어|출고용|출고때|출고 시).{0,40}(?:품번|부품\s*번호|파트\s*넘버|part\s*number)|"
    r"(?:품번|부품\s*번호|파트\s*넘버|part\s*number).{0,40}(?:\bOE\b|순정|출고\s*타이어|출고용|출고때|출고 시)",
    re.IGNORECASE,
)
_MILEAGE_ATTRIBUTE_RE = re.compile(
    r"오래\s*(?:타|탈)|수명|내구|마일리지\s*(?:타이어|좋|높|긴)|long",
    re.IGNORECASE,
)
_MILEAGE_PRODUCT_RE = re.compile(r"마일리지\s*(?:플러스|plus|\d)|mileage\s*plus", re.IGNORECASE)
_LATEST_RE = re.compile(r"최신|신상|신제품|최근(?:에)?\s*(?:출시|나온)|새로\s*나온|등록일", re.IGNORECASE)
_CONCEPT_RE = re.compile(r"뭐야|무슨\s*뜻|의미|차이|설명", re.IGNORECASE)
_BUY_RE = re.compile(r"구매|살래|주문|장바구니|결제", re.IGNORECASE)
_PRICE_OR_COUPON_RE = re.compile(r"가격|얼마|할인가|최대\s*혜택|쿠폰|할인|혜택", re.IGNORECASE)
_STOCK_OR_BOOKING_RE = re.compile(r"재고|오늘\s*장착|장착\s*가능|예약|매장|근처|주변", re.IGNORECASE)
_VEHICLE_SIZE_LOOKUP_RE = re.compile(
    r"(?:내\s*차|내차|내\s*차량|내차량|등록\s*차량|등록차).{0,24}(?:타이어\s*사이즈|타이어\s*규격|규격)|"
    r"(?:타이어\s*사이즈|타이어\s*규격|규격).{0,24}(?:내\s*차|내차|내\s*차량|내차량|등록\s*차량|등록차)",
    re.IGNORECASE,
)
_SIMILAR_PRICE_RE = re.compile(r"비슷한\s*가격|가격대|동급\s*가격", re.IGNORECASE)
_QUANTITY_OPTION_RE = re.compile(r"(\d{1,2})\s*(?:개|본)")
_QUANTITY_BENEFIT_RE = re.compile(r"할인|혜택|가격|금액|최종가|저렴|싼|싸|쿠폰", re.IGNORECASE)
_QUANTITY_COMPARE_RE = re.compile(r"비교|중에|살까|고민|더|차이|낫|유리|얼마나", re.IGNORECASE)
_GRADE_COMPARE_RE = re.compile(r"프리미엄|등급|상위|하위|급", re.IGNORECASE)
_COMPARE_RE = re.compile(r"비교|차이|무슨\s*차이|뭐가\s*달라|보다|중에|가장|제일|맞지|아냐", re.IGNORECASE)
_RECOMMEND_RE = re.compile(r"추천|찾|골라|보여|알려", re.IGNORECASE)
_BEST_SELLER_RE = re.compile(
    r"인기|베스트\s*셀러|베스트|잘\s*팔리|많이\s*팔(?:린|리는)|많이\s*(?:사는|구매한|산)|"
    r"(?:젤|제일|가장)\s*많이\s*(?:사는|구매한|산|팔(?:린|리는))|잘\s*나가|"
    r"최다\s*(?:판매|구매)|판매\s*(?:순위|랭킹|량)|구매\s*(?:순위|랭킹)",
    re.IGNORECASE,
)
_BEST_SELLER_AGGREGATE_RE = re.compile(
    r"베스트\s*셀러|"
    r"판매\s*(?:순위|랭킹|량)|구매\s*(?:순위|랭킹)|최다\s*(?:판매|구매)|"
    r"(?=.*(?:타이어|상품|제품|것|거))"
    r"(?=.*(?:베스트|인기|잘\s*팔리|많이\s*(?:사는|구매한|산|팔(?:린|리는))|"
    r"(?:젤|제일|가장)\s*많이\s*(?:사는|구매한|산|팔(?:린|리는))|잘\s*나가|"
    r"최다\s*(?:판매|구매)|판매\s*(?:순위|랭킹|량)|구매\s*(?:순위|랭킹)))",
    re.IGNORECASE,
)
_BEST_SELLER_UNSPECIFIED_COMMERCE_RE = re.compile(
    r"(?=.*(?:요즘|최근|지금|현재))"
    r"(?=.*(?:것|거|타이어|상품))"
    r"(?=.*(?:인기\s*(?:있|많)|잘\s*팔리|잘\s*나가|"
    r"많이\s*팔(?:린|리는)|"
    r"(?:젤|제일|가장)\s*(?:인기|많이\s*(?:사는|구매한|산|팔(?:린|리는)))))",
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
    r"진행\s*중인\s*(?:이벤트|행사|혜택|기획전|프로모션)|이벤트\s*/\s*기획전|이벤트랑\s*기획전|"
    r"이벤트(?:와|과|하고)\s*기획전|기획전(?:와|과|하고)\s*이벤트|"
    r"(?:지금|현재)?\s*(?:이벤트|기획전|프로모션|행사|혜택)\s*(?:뭐\s*있|뭐가\s*있|있어|있냐|목록|리스트|검색|조회|보여|알려)|"
    r"이벤트\s*혜택\s*(?:목록|리스트|검색|조회|보여|알려)?|"
    r"이벤트\s*(?:목록|리스트|검색|조회|보여|알려)",
    re.IGNORECASE,
)
_DEAL_LIST_RE = re.compile(
    r"기획전\s*(?:상품|적용\s*상품|대상\s*상품|에서\s*살\s*수\s*있는\s*상품)",
    re.IGNORECASE,
)
_PRODUCT_EVENT_LOOKUP_RE = re.compile(r"행사|이벤트|프로모션", re.IGNORECASE)
_PRODUCT_DEAL_LOOKUP_RE = re.compile(r"기획전|딜|deal", re.IGNORECASE)
_PRODUCT_COUPON_LOOKUP_RE = re.compile(r"쿠폰|할인권", re.IGNORECASE)
_PRODUCT_BENEFIT_LOOKUP_RE = re.compile(r"행사|이벤트|프로모션|기획전|딜|deal|쿠폰|할인권|혜택", re.IGNORECASE)
_BENEFIT_STACKING_RE = re.compile(r"중복|같이|함께|동시|둘\s*다|다\s*돼|같이\s*돼", re.IGNORECASE)
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
    ("car_type", re.compile(r"차종|승용\s*/\s*suv|suv\s*용|승용차용|전기차용|전기차\s*전용|승용차\s*대비|suv\s*대비", re.IGNORECASE)),
)
_REQUESTED_PRODUCT_ATTRIBUTE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("brand", re.compile(r"브랜드|brand", re.IGNORECASE)),
    ("manufacturer", re.compile(r"제조사|제조원|만든\s*회사|어디꺼|어느\s*회사", re.IGNORECASE)),
    ("origin", re.compile(r"원산지|생산국|제조국|어느\s*나라", re.IGNORECASE)),
    ("release", re.compile(r"출시|출시일|출시년도|등록일", re.IGNORECASE)),
    ("noise", _NOISE_LABEL_RE),
    ("fuel_efficiency", re.compile(r"연비|회전\s*저항|rr\b", re.IGNORECASE)),
    ("wet", re.compile(r"빗길|젖은\s*노면|젖은노면|wet|제동\s*등급", re.IGNORECASE)),
    ("price_grade", re.compile(r"상품\s*등급|가격\s*등급|프리미엄|스탠다드|이코노미", re.IGNORECASE)),
    ("season", re.compile(r"계절|사계절|겨울용|여름용|올웨더|올시즌", re.IGNORECASE)),
    ("car_type", re.compile(r"차종|승용\s*/\s*suv|suv\s*용|승용차용|전기차용|전기차\s*전용|승용차\s*대비|suv\s*대비", re.IGNORECASE)),
    ("price", re.compile(r"가격\s*비교|가격\s*차이|더\s*싸|더\s*비싸|가격은\s*얼마|얼마나\s*저렴", re.IGNORECASE)),
    ("mileage", _MILEAGE_ATTRIBUTE_RE),
    ("load", re.compile(r"하중|하중지수|무게", re.IGNORECASE)),
    ("speed", re.compile(r"속도\s*기호|속도|고속", re.IGNORECASE)),
)
_REQUESTED_PRODUCT_ATTRIBUTES = frozenset(metric for metric, _ in _REQUESTED_PRODUCT_ATTRIBUTE_PATTERNS)
_RECOMMENDATION_ATTRIBUTE_METRICS: frozenset[str] = frozenset(
    {"fuel_efficiency", "wet", "load", "speed"}
)
_CLAIM_CHECK_VERIFICATION_RE = re.compile(r"맞아|사실|진짜|확인|검증|이라던데|라던데", re.IGNORECASE)
_UNVERIFIED_EXTERNAL_CLAIM_RE = re.compile(
    r"우주|항공|nasa|나사|인증|공인|군용|전투기|특허|1\s*위|세계\s*최고|공식",
    re.IGNORECASE,
)

_PRODUCT_ALIASES: tuple[tuple[str, str, str], ...] = (
    ("ventus air s", "Ventus air S", "HK"),
    ("벤투스 air s", "Ventus air S", "HK"),
    ("벤투스 에어 s", "Ventus air S", "HK"),
    ("벤투스 에어s", "Ventus air S", "HK"),
    ("ventus s2 as", "Ventus S2 AS", "HK"),
    ("벤투스 s2 as", "Ventus S2 AS", "HK"),
    ("ventus s2", "Ventus S2", "HK"),
    ("벤투스 s2", "Ventus S2", "HK"),
    ("ventus s1 evo z as", "Ventus S1 evo Z AS", "HK"),
    ("벤투스 s1 evo z as", "Ventus S1 evo Z AS", "HK"),
    ("벤투스 s1 에보 z as", "Ventus S1 evo Z AS", "HK"),
    ("ventus s1 evo z", "Ventus S1 evo Z", "HK"),
    ("벤투스 s1 evo z", "Ventus S1 evo Z", "HK"),
    ("벤투스 s1 에보 z", "Ventus S1 evo Z", "HK"),
    ("dynapro hpx", "Dynapro HPX", "HK"),
    ("다이나프로 hpx", "Dynapro HPX", "HK"),
    ("dynapro hp3", "Dynapro HP3", "HK"),
    ("다이나프로 hp3", "Dynapro HP3", "HK"),
    ("kinergy ex", "Kinergy EX", "HK"),
    ("키너지 ex", "Kinergy EX", "HK"),
    ("kinergy 4s2", "키너지 4S2", "HK"),
    ("키너지 4s2", "키너지 4S2", "HK"),
    ("키너지4s2", "키너지 4S2", "HK"),
    ("kinergy st as", "Kinergy ST AS", "HK"),
    ("키너지 st as", "Kinergy ST AS", "HK"),
    ("weatherflex gt", "웨더플렉스 GT", "HK"),
    ("웨더플렉스 gt", "웨더플렉스 GT", "HK"),
    ("ion evo as", "iON evo AS", "HK"),
    ("아이온 evo as", "iON evo AS", "HK"),
    ("아이온 에보 as", "iON evo AS", "HK"),
    ("ion evo as suv", "iON evo AS SUV", "HK"),
    ("아이온 evo as suv", "iON evo AS SUV", "HK"),
    ("아이온 에보 as suv", "iON evo AS SUV", "HK"),
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
    ("마일리지 플러스", "Mileage Plus", "HK"),
    ("mileage plus", "Mileage Plus", "HK"),
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
_PRODUCT_FAMILY_ALIASES: tuple[tuple[str, str, str], ...] = (
    ("ventus", "Ventus", "HK"),
    ("벤투스", "Ventus", "HK"),
    ("dynapro", "Dynapro", "HK"),
    ("다이나프로", "Dynapro", "HK"),
    ("kinergy", "Kinergy", "HK"),
    ("키너지", "Kinergy", "HK"),
    ("ion", "iON", "HK"),
    ("아이온", "iON", "HK"),
    ("optimo", "Optimo", "HK"),
    ("옵티모", "Optimo", "HK"),
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
    return f"{match.group(1)}/{match.group(2)}{match.group(3)}R{match.group(4)}"


def extract_product_names(text: str) -> tuple[str, ...]:
    normalized = (text or "").casefold()
    matches: list[tuple[int, int, str]] = []
    seen_spans: set[tuple[int, int, str]] = set()
    for needle, display_name, _brand_cd in _PRODUCT_ALIASES:
        needle_norm = needle.casefold()
        start = normalized.find(needle_norm)
        while start >= 0:
            end = start + len(needle_norm)
            key = (start, end, display_name)
            if key not in seen_spans:
                matches.append(key)
                seen_spans.add(key)
            start = normalized.find(needle_norm, start + 1)

    matches.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))
    selected_spans: list[tuple[int, int, str]] = []
    for start, end, display_name in matches:
        if any(not (end <= chosen_start or start >= chosen_end) for chosen_start, chosen_end, _ in selected_spans):
            continue
        selected_spans.append((start, end, display_name))

    selected_spans.sort(key=lambda item: item[0])
    products: list[str] = []
    for _start, _end, display_name in selected_spans:
        if display_name not in products:
            products.append(display_name)
    return tuple(products)


def extract_product_family_names(text: str) -> tuple[str, ...]:
    normalized = (text or "").casefold()
    product_spans: list[tuple[int, int]] = []
    for needle, _display_name, _brand_cd in _PRODUCT_ALIASES:
        needle_norm = needle.casefold()
        start = normalized.find(needle_norm)
        while start >= 0:
            product_spans.append((start, start + len(needle_norm)))
            start = normalized.find(needle_norm, start + 1)

    family_matches: list[tuple[int, int, str]] = []
    seen: set[tuple[int, int, str]] = set()
    for needle, display_name, _brand_cd in _PRODUCT_FAMILY_ALIASES:
        needle_norm = needle.casefold()
        start = normalized.find(needle_norm)
        while start >= 0:
            end = start + len(needle_norm)
            if needle_norm == "ion":
                prev_char = normalized[start - 1] if start > 0 else ""
                next_char = normalized[end] if end < len(normalized) else ""
                if prev_char.isalpha() or next_char.isalpha():
                    start = normalized.find(needle_norm, start + 1)
                    continue
            if any(not (end <= product_start or start >= product_end) for product_start, product_end in product_spans):
                start = normalized.find(needle_norm, start + 1)
                continue
            key = (start, end, display_name)
            if key not in seen:
                family_matches.append(key)
                seen.add(key)
            start = normalized.find(needle_norm, start + 1)

    family_matches.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))
    selected: list[tuple[int, int, str]] = []
    for start, end, display_name in family_matches:
        if any(not (end <= chosen_start or start >= chosen_end) for chosen_start, chosen_end, _ in selected):
            continue
        selected.append((start, end, display_name))
    selected.sort(key=lambda item: item[0])

    families: list[str] = []
    for _start, _end, display_name in selected:
        if display_name not in families:
            families.append(display_name)
    return tuple(families)


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


def _reorder_grade_compare_products(text: str, products: tuple[str, ...]) -> tuple[str, ...]:
    if len(products) < 2 or "보다" not in (text or ""):
        return products
    normalized = (text or "").casefold()
    positions: dict[str, int] = {}
    for product in products:
        best = -1
        for needle, display_name, _brand_cd in _PRODUCT_ALIASES:
            if display_name != product:
                continue
            pos = normalized.find(needle.casefold())
            if pos >= 0 and (best < 0 or pos < best):
                best = pos
        if best >= 0:
            positions[product] = best
    pivot = normalized.find("보다")
    after = [product for product in products if positions.get(product, -1) > pivot]
    before = [product for product in products if product not in after]
    if not after and len(before) >= 2:
        before = sorted(before, key=lambda product: positions.get(product, -1), reverse=True)
        return tuple(before)
    return tuple(after + before) if after and before else products


def extract_brand_code(text: str) -> str | None:
    brand_codes = extract_brand_codes(text)
    return brand_codes[0] if brand_codes else None


def extract_product_brand_code(text: str) -> str | None:
    normalized = (text or "").casefold()
    for needle, _display_name, brand_cd in _PRODUCT_ALIASES:
        if needle.casefold() in normalized:
            return brand_cd
    for needle, _display_name, brand_cd in _PRODUCT_FAMILY_ALIASES:
        if needle.casefold() in normalized:
            return brand_cd
    return None


def extract_product_attribute_metrics(text: str) -> tuple[str, ...]:
    metrics: list[str] = []
    for metric, pattern in _PRODUCT_ATTRIBUTE_PATTERNS:
        if pattern.search(text or "") and metric not in metrics:
            metrics.append(metric)
    return tuple(metrics)


def extract_requested_product_attribute(text: str) -> str | None:
    for requested_attribute, pattern in _REQUESTED_PRODUCT_ATTRIBUTE_PATTERNS:
        if pattern.search(text or ""):
            return requested_attribute
    return None


def extract_oe_replacement_type(text: str) -> str | None:
    for replacement_type, pattern in _OE_REPLACEMENT_TYPE_PATTERNS:
        if pattern.search(text or ""):
            return replacement_type
    return None


def classify_product_claim_check_type(text: str) -> str:
    """Classify whether a product turn asks for claim verification.

    Keep the classification in policy space so response formatters only consume
    the structured result and never inspect individual claim words.
    """
    text = text or ""
    if not extract_product_names(text) or not _CLAIM_CHECK_VERIFICATION_RE.search(text):
        return "none"
    if extract_product_attribute_metrics(text):
        return "verifiable_product_attribute"
    if _UNVERIFIED_EXTERNAL_CLAIM_RE.search(text):
        return "unverified_external_claim"
    return "none"


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
    if _BEST_SELLER_RE.search(text) and (
        _BEST_SELLER_AGGREGATE_RE.search(text)
        or _BEST_SELLER_UNSPECIFIED_COMMERCE_RE.search(text)
    ):
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


def best_seller_search_params_from_text(text: str) -> dict[str, str | int]:
    text = text or ""
    if not is_best_seller_request(text):
        return {}

    today = date.today()
    if _BEST_SELLER_DAY_RE.search(text):
        iso_today = today.isoformat()
        return {"from_date": iso_today, "to_date": iso_today}
    if _BEST_SELLER_WEEK_RE.search(text):
        week_start = today - timedelta(days=today.weekday())
        return {"from_date": week_start.isoformat(), "to_date": today.isoformat()}
    if _BEST_SELLER_MONTH_RE.search(text):
        month_start = today.replace(day=1)
        return {"from_date": month_start.isoformat(), "to_date": today.isoformat()}

    month_match = re.search(r"(?<!\d)(3|6|12)\s*개\s*월|(?<!\d)(3|6|12)\s*개월", text)
    if month_match:
        month_value = next((group for group in month_match.groups() if group), None)
        if month_value is not None:
            return {"months": int(month_value)}
    if re.search(r"\b1\s*년\b|최근\s*1\s*년|12\s*개월", text):
        return {"months": 12}
    return {}


_BEST_SELLER_VEHICLE_STRIP_RE = re.compile(
    r"(?:최근\s*\d+\s*개월|오늘|이번\s*주|금주|이번\s*달|이달|월별|분기|요즘|최근|지금|"
    r"가장|제일|잘\s*팔리는|잘\s*나가는|많이\s*(?:팔린|산|구매한)|인기\s*(?:있는?|많(?:은|이)?)|"
    r"베스트셀러|베스트\s*셀러|상품|제품|타이어|추천해줘|보여줘|알려줘|뭐야|\?|!)",
    re.IGNORECASE,
)
_BEST_SELLER_NON_VEHICLE_ONLY_RE = re.compile(
    r"^(?:\d+\s*개월?|오늘|이번\s*주|금주|이번\s*달|이달|월별|분기|요즘|최근|지금|\s)+$",
    re.IGNORECASE,
)
_BEST_SELLER_VEHICLE_TOKEN_STOPWORDS = {
    "요즘", "최근", "지금", "젤", "제일", "가장", "거", "것", "상품", "제품", "타이어", "인기", "있는", "많이",
    "팔리는", "팔린", "팔리는거", "팔린거", "잘", "나가는", "베스트셀러", "선호하는", "좋아하는", "추천",
    "추천해줘", "알려줘", "보여줘", "순위", "판매량", "는", "가", "이", "좀",
}
_BEST_SELLER_VEHICLE_TRAILING_PARTICLE_RE = re.compile(r"(?:에서|으로|로|에|은|는|이|가|도|만|과|와)$")
_GENERAL_BEST_SELLER_SCOPE_RE = re.compile(
    r"^(?:전체|전부|모든|통합)?\s*(?:베스트\s*셀러|베스트셀러|인기\s*(?:상품|제품|타이어)|잘\s*팔리는\s*타이어)"
    r"\s*(?:보기|보여줘|알려줘|확인|목록)?$",
    re.IGNORECASE,
)


def is_general_best_seller_scope_request(text: str) -> bool:
    text = re.sub(r"\s+", " ", str(text or "")).strip(" ,.?!")
    if not text or not is_best_seller_request(text):
        return False
    return bool(_GENERAL_BEST_SELLER_SCOPE_RE.fullmatch(text))


def extract_best_seller_vehicle_query(text: str) -> str | None:
    text = str(text or "").strip()
    if not text or not is_best_seller_request(text):
        return None
    if is_general_best_seller_scope_request(text):
        return None
    if _DEMOGRAPHIC_ATTRIBUTE_RE.search(text) and _DEMOGRAPHIC_PREFERENCE_RE.search(text):
        return None
    vehicle_model_match = match_vehicle_model_category(text)
    if vehicle_model_match is not None:
        return vehicle_model_match.vehicle_query

    candidate = _BEST_SELLER_VEHICLE_STRIP_RE.sub(" ", text)
    candidate = re.sub(r"\s+", " ", candidate).strip(" ,.")
    if not candidate or _BEST_SELLER_NON_VEHICLE_ONLY_RE.fullmatch(candidate):
        return None
    if normalize_tire_size(candidate):
        return None
    if re.fullmatch(r"(?:남성|여성|\d{2}대|\d{2}대\s*(?:남성|여성)?)", candidate):
        return None
    tokens = [
        token for token in re.split(r"\s+", candidate)
        if token and token not in _BEST_SELLER_VEHICLE_TOKEN_STOPWORDS
    ]
    tokens = [
        token
        for token in tokens
        if len(token) >= 2 or re.search(r"[A-Za-z0-9]", token)
    ]
    if not tokens:
        return None
    cleaned_candidate = " ".join(tokens).strip()
    cleaned_candidate = _BEST_SELLER_VEHICLE_TRAILING_PARTICLE_RE.sub("", cleaned_candidate).strip()
    if not cleaned_candidate or cleaned_candidate in _BEST_SELLER_VEHICLE_TOKEN_STOPWORDS:
        return None
    return cleaned_candidate


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
    inherited_tire_size = normalize_tire_size(str(slots.get("tire_size") or ""))
    allow_inherited_tire_size = slots.get("allow_inherited_tire_size", True)
    tire_size = explicit_tire_size or (inherited_tire_size if allow_inherited_tire_size else None)
    products = extract_product_names(text)
    product_families = () if products else extract_product_family_names(text)
    attribute_metrics = extract_product_attribute_metrics(text)
    requested_product_attribute = str(
        slots.get("requested_product_attribute") or extract_requested_product_attribute(text) or ""
    ).strip()
    oe_replacement_type = extract_oe_replacement_type(text)
    brand_codes = extract_brand_codes(text)
    variant_constraints = extract_variant_constraints(text)
    brand_cd = brand_codes[0] if brand_codes else extract_product_brand_code(text)
    quantity_options = extract_quantity_options(text)
    discovery_followup_intent = str(slots.get("discovery_followup_intent") or "").strip()
    recent_product_set_followup_type = str(slots.get("recent_product_set_followup_type") or "").strip()
    recent_product_set_metric = str(slots.get("recent_product_set_metric") or "").strip()
    recent_product_set_direction = str(slots.get("recent_product_set_direction") or "").strip()
    recent_product_set_price_basis = str(slots.get("recent_product_set_price_basis") or "").strip()
    comparison_followup_intent = str(slots.get("comparison_followup_intent") or "").strip()
    comparison_metric = str(slots.get("comparison_metric") or "").strip()
    discovery_followup_action = str(slots.get("discovery_followup_action") or "").strip()
    router_recommendation_scenario = str(slots.get("recommendation_scenario") or "").strip()
    recommendation_context = _recommendation_context_dict(slots.get("recommendation_context"))
    context_recommendation_scenario = str(
        (recommendation_context or {}).get("recommendation_scenario")
        or (recommendation_context or {}).get("scenario")
        or ""
    ).strip()
    general_tire_recommendation = _is_general_tire_recommendation_request(text)
    if (
        requested_product_attribute == "car_type"
        and _GENERAL_TIRE_RECOMMENDATION_ACTION_RE.search(text)
        and not _CONCEPT_RE.search(text)
    ):
        requested_product_attribute = ""

    entities: dict[str, Any] = {
        "product_names": products,
        "product_family_names": product_families,
        "tire_size": tire_size,
        "explicit_tire_size": explicit_tire_size,
        "purchase_intent": bool(_BUY_RE.search(text)),
        "attribute_metrics": attribute_metrics,
        "claim_check_type": classify_product_claim_check_type(text),
    }
    if requested_product_attribute in _REQUESTED_PRODUCT_ATTRIBUTES:
        entities["requested_product_attribute"] = requested_product_attribute
    if oe_replacement_type:
        entities["oe_replacement_type"] = oe_replacement_type
    if quantity_options:
        entities["quantity_options"] = quantity_options
    if discovery_followup_intent == "recent_product_set_size_availability":
        entities["discovery_followup_intent"] = discovery_followup_intent
    if recent_product_set_followup_type == "rank_recent_product_set":
        entities["recent_product_set_followup_type"] = recent_product_set_followup_type
    if recent_product_set_metric in {
        "price", "noise", "wet", "snow", "release", "review", "rating", "grade", "vehicle_type", "mileage", "detail",
    }:
        entities["recent_product_set_metric"] = recent_product_set_metric
    if recent_product_set_direction in {"min", "max", "match", "compare"}:
        entities["recent_product_set_direction"] = recent_product_set_direction
    if recent_product_set_price_basis in {"cheapest_final_prc", "extra_fvr_sale_prc", "sale_prc"}:
        entities["recent_product_set_price_basis"] = recent_product_set_price_basis
    if comparison_followup_intent in {
        "continue_previous_compare_metric",
        "new_compare_metric",
        "generic_compare",
    }:
        entities["comparison_followup_intent"] = comparison_followup_intent
    if comparison_metric in {
        "release", "price", "grade", "mileage", "noise", "fuel_efficiency", "wet", "car_type", "detail",
    }:
        entities["compare_metric"] = comparison_metric
    if discovery_followup_action == "vehicle_based_recommendation_refinement":
        entities["discovery_followup_action"] = discovery_followup_action
    elif discovery_followup_action == "vehicle_resolved_recommendation":
        entities["discovery_followup_action"] = discovery_followup_action
        named_vehicle_anchor = str(slots.get("named_registered_vehicle_anchor") or "").strip()
        if named_vehicle_anchor:
            entities["named_registered_vehicle_anchor"] = named_vehicle_anchor
    elif _MY_VEHICLE_RECOMMENDATION_RE.search(text) and (_RECOMMEND_RE.search(text) or _COMPARE_RE.search(text)):
        entities["discovery_followup_action"] = "vehicle_resolved_recommendation"
        named_vehicle_anchor = _named_my_vehicle_anchor(text)
        if named_vehicle_anchor:
            entities["named_registered_vehicle_anchor"] = named_vehicle_anchor
    if has_registered_vehicle_size_lookup_signal(text):
        entities["vehicle_information_request"] = "tire_size_lookup"
        named_vehicle_anchor = _named_my_vehicle_anchor(text)
        if named_vehicle_anchor:
            entities["named_registered_vehicle_anchor"] = named_vehicle_anchor
    elif has_registered_vehicle_type_query_signal(text):
        entities["vehicle_information_request"] = "vehicle_type_lookup"
        named_vehicle_anchor = _named_my_vehicle_anchor(text)
        if named_vehicle_anchor:
            entities["named_registered_vehicle_anchor"] = named_vehicle_anchor
    vehicle_model_match = match_vehicle_model_category(text)
    # Scenario keywords inside a matched car model name (e.g. "스포츠" in
    # "렉스턴 스포츠") are not scenario intent — extract from masked text.
    scenario_text = vehicle_model_match.masked_text if vehicle_model_match is not None else text
    scenario = recommendation_scenario_from_text(
        scenario_text,
        router_recommendation_scenario or context_recommendation_scenario,
    )
    if general_tire_recommendation:
        scenario = None
    product_resolution_transaction_anchor = bool(
        (products or product_families)
        and (
            entities["purchase_intent"]
            or _PRICE_OR_COUPON_RE.search(text)
            or _STOCK_OR_BOOKING_RE.search(text)
            or _RESTOCK_RE.search(text)
        )
    )
    if scenario is not None:
        entities.update(recommendation_scenario_metadata(scenario))
        entities["recommendation_scenario_tool_args_patch"] = dict(scenario.tool_args_patch)
    if recommendation_context:
        entities["recommendation_context"] = {
            key: value for key, value in recommendation_context.items() if value not in (None, "")
        }
    if len(products) >= 2:
        entities["multi_product_names"] = True
        if _MULTI_PRODUCT_DESCRIPTION_RE.search(text):
            entities["multi_product_description_request"] = True
        if re.search(
            r"각각|둘\s*다|둘\s*모두|상품\s*정보|설명|알려|(?:상품\s*)?(?:추천|검색|찾아|보여)",
            text,
            re.IGNORECASE,
        ):
            entities["multi_product_detail_request"] = True
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

    if _PERFORMANCE_RE.search(scenario_text):
        entities["performance"] = "performance"
    if _QUIET_RECOMMENDATION_RE.search(scenario_text):
        entities["quiet_focus"] = True
    if general_tire_recommendation:
        entities["vehicle_category"] = "passenger"
        entities["general_tire_preference"] = "non_ev"
        entities["rcmd_type"] = "tstation"
    elif _EV_RECOMMENDATION_RE.search(text):
        entities["vehicle_category"] = "ev"
    elif _SUV_RECOMMENDATION_RE.search(text):
        entities["vehicle_category"] = "suv"
    elif _TRUCK_VAN_RECOMMENDATION_RE.search(text):
        entities["vehicle_category"] = "truck_van"
    elif _PASSENGER_RECOMMENDATION_RE.search(text):
        entities["vehicle_category"] = "passenger"
    elif vehicle_model_match is not None:
        entities["vehicle_category"] = vehicle_model_match.category
        entities["vehicle_model_name"] = vehicle_model_match.model
        entities["vehicle_category_source"] = "model_inference"
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
    price_range = _price_range_from_text(text)
    if not price_range:
        allow_inherited_price_range = slots.get("allow_inherited_price_range", True)
        if allow_inherited_price_range:
            inherited_price_range = {
                key: (slots.get(key) if slots.get(key) is not None else recommendation_context.get(key))
                for key in ("min_price", "max_price")
            }
            price_range = {
                key: value for key, value in inherited_price_range.items() if value is not None
            }
    if price_range:
        entities["price_range"] = price_range
        entities.update(price_range)
    if is_external_price_comparison_request(text, known_slots=slots):
        entities["external_price_comparison"] = True
    if _OE_PART_NUMBER_REQUEST_RE.search(text):
        entities["oe_part_number_request"] = True
    best_seller_period = best_seller_period_from_text(text)
    if best_seller_period:
        entities["best_seller_period"] = best_seller_period
        entities.update(best_seller_search_params_from_text(text))
        best_seller_vehicle_query = ""
        if is_general_best_seller_scope_request(text):
            best_seller_vehicle_query = ""
        elif vehicle_model_match is not None:
            best_seller_vehicle_query = vehicle_model_match.vehicle_query
        else:
            best_seller_vehicle_query = extract_best_seller_vehicle_query(text) or ""
        if best_seller_vehicle_query:
            entities["vehicle_query"] = best_seller_vehicle_query
    if is_default_tire_shopping_request(text):
        entities["default_tire_shopping"] = True
    if is_default_benefit_request(text):
        entities["default_benefit"] = True
    elif is_deal_list_request(text):
        entities["deal_list_only"] = True
    if products and _PRODUCT_BENEFIT_LOOKUP_RE.search(text) and not _BENEFIT_STACKING_RE.search(text):
        if _PRODUCT_EVENT_LOOKUP_RE.search(text):
            entities["product_benefit_lookup_type"] = "event"
        elif _PRODUCT_DEAL_LOOKUP_RE.search(text):
            entities["product_benefit_lookup_type"] = "deal"
        elif _PRODUCT_COUPON_LOOKUP_RE.search(text):
            entities["product_benefit_lookup_type"] = "coupon"
        else:
            entities["product_benefit_lookup_type"] = "benefit"

    concept = bool(_CONCEPT_RE.search(text))
    standalone_attribute_metrics = tuple(
        metric for metric in attribute_metrics if metric not in ("season", "car_type")
    )
    if discovery_followup_action == "vehicle_based_recommendation_refinement":
        intent = "product_recommendation"
        sub_intent = "vehicle_based_recommendation_refinement"
    elif entities.get("discovery_followup_action") == "vehicle_resolved_recommendation":
        intent = "product_recommendation"
        sub_intent = "vehicle_resolved_recommendation"
    elif entities.get("vehicle_information_request") in ("tire_size_lookup", "vehicle_type_lookup"):
        intent = "product_description"
        sub_intent = "vehicle_information"
    elif (
        oe_replacement_type == "oe"
        and entities.get("oe_part_number_request")
    ):
        intent = "product_description"
        sub_intent = "oe_part_number_unavailable"
    elif (
        oe_replacement_type
        and (
            tire_size
            or products
            or brand_cd
        )
    ):
        intent = "product_search"
        sub_intent = "oe_re_product_filter"
    elif (
        oe_replacement_type
        and (
            concept
            or not products
        )
    ):
        intent = "product_description"
        sub_intent = "oe_re_concept_explanation"
    elif (
        discovery_followup_intent == "recent_product_set_size_availability"
        and tire_size
        and not products
    ):
        intent = "product_search"
        sub_intent = "recent_product_set_size_availability"
    elif recent_product_set_followup_type == "rank_recent_product_set" and recent_product_set_metric:
        intent = "product_search"
        sub_intent = "recent_product_set_ranking"
    elif (
        len(products) >= 2
        and comparison_followup_intent == "continue_previous_compare_metric"
        and comparison_metric in {"release", "price", "grade", "mileage", "noise", "fuel_efficiency", "wet", "car_type", "detail"}
    ):
        intent = "product_comparison"
        sub_intent = (
            "latest_compare"
            if comparison_metric == "release"
            else "grade_compare"
            if comparison_metric == "grade"
            else "mileage_compare"
            if comparison_metric == "mileage"
            else "attribute_compare"
        )
    elif (
        len(products) >= 2
        and comparison_followup_intent == "new_compare_metric"
        and comparison_metric in {"release", "price", "grade", "mileage", "noise", "fuel_efficiency", "wet", "car_type", "detail"}
    ):
        intent = "product_comparison"
        sub_intent = (
            "latest_compare"
            if comparison_metric == "release"
            else "grade_compare"
            if comparison_metric == "grade"
            else "mileage_compare"
            if comparison_metric == "mileage"
            else "attribute_compare"
        )
    elif (
        len(products) >= 2
        and comparison_followup_intent == "generic_compare"
        and not entities.get("multi_product_description_request")
    ):
        intent = "product_comparison"
        sub_intent = "general_compare"
        entities.setdefault("compare_metric", "detail")
    elif entities.get("external_price_comparison"):
        intent = "product_search"
        sub_intent = "external_price_comparison_request"
    elif entities.get("product_benefit_lookup_type") == "event":
        intent = "product_search"
        sub_intent = "product_event_lookup"
    elif entities.get("product_benefit_lookup_type") == "deal":
        intent = "product_search"
        sub_intent = "product_deal_lookup"
    elif entities.get("product_benefit_lookup_type") == "coupon":
        intent = "product_search"
        sub_intent = "product_coupon_lookup"
    elif entities.get("product_benefit_lookup_type") == "benefit":
        intent = "product_search"
        sub_intent = "product_benefit_lookup"
    elif entities.get("default_benefit"):
        intent = "product_search"
        sub_intent = "benefit_event_list_lookup"
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
    elif product_resolution_transaction_anchor:
        intent = "product_search"
        if products and _RESTOCK_RE.search(text):
            sub_intent = "restock_inquiry"
            entities["restock_inquiry"] = True
        else:
            sub_intent = "product_family_search" if product_families else "product_name_search"
        entities["product_keyword"] = (product_families or products)[0]
    elif _OCCUPATION_RE.search(text) and _MILEAGE_ATTRIBUTE_RE.search(text):
        intent = "product_description"
        sub_intent = "mileage_bias_guardrail"
        entities["compare_metric"] = "mileage"
        entities["guardrail"] = "occupation_neutral"
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
    elif len(products) >= 2 and _COMPARE_RE.search(text):
        intent = "product_comparison"
        sub_intent = "general_compare"
    elif concept and _SOUND_ABSORBER_RE.search(text) and entities["purchase_intent"]:
        intent = "product_recommendation"
        sub_intent = "technology_explain_then_recommend"
    elif variant_constraints and len(variant_constraints) >= 2:
        intent = "product_recommendation"
        sub_intent = "general_recommendation"
    elif concept and _WINTER_RE.search(text) and _ALL_SEASON_RE.search(text):
        intent = "product_description"
        sub_intent = "season_concept_compare"
    elif requested_product_attribute == "car_type" and concept and not general_tire_recommendation:
        intent = "product_description"
        sub_intent = "product_attribute_explanation"
        entities["compare_metric"] = "car_type"
    elif requested_product_attribute and products:
        intent = "product_description"
        sub_intent = "product_attribute_lookup"
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
    elif entities.get("claim_check_type") == "unverified_external_claim" and products:
        intent = "product_description"
        sub_intent = "product_claim_check"
    elif _SIMILAR_PRICE_RE.search(text):
        intent = "product_recommendation"
        sub_intent = "similar_price_recommendation"
    elif (
        _SOUND_ABSORBER_RE.search(text)
        or _SAFE_SERVICE_RE.search(text)
        or _PERFORMANCE_RE.search(text)
        or _LOWEST_PRICE_RE.search(text)
        or scenario is not None
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
    if (
        intent == "product_recommendation"
        and not tire_size
        and (
            discovery_followup_action == "vehicle_based_recommendation_refinement"
            or entities.get("discovery_followup_action") == "vehicle_resolved_recommendation"
        )
    ):
        missing_slots = ("tire_size",)
    elif intent == "product_recommendation" and not tire_size and entities.get("price_goal") == "lowest":
        missing_slots = ("tire_size",)
    elif sub_intent == "quantity_benefit_comparison" and not tire_size and not slots.get("goods_no"):
        missing_slots = ("tire_size",)

    if sub_intent == "grade_compare":
        products = _reorder_grade_compare_products(text, products)
        entities["product_names"] = products

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
    tire_size = entities.get("tire_size")
    if frame.sub_intent == "vehicle_information":
        return ToolPlan(
            allowed_tools=("get_my_cars_tool",),
            preferred_tool="get_my_cars_tool",
            metadata={"response_intent": "vehicle_information"},
        )
    if frame.sub_intent == "oe_re_product_filter":
        args = {"limit": 10}
        product_names = entities.get("product_names") or ()
        if product_names:
            args["keyword"] = product_names[0]
        if entities.get("tire_size"):
            args["size"] = entities["tire_size"]
        if entities.get("brand_cd"):
            args["brand_cd"] = entities["brand_cd"]
        return ToolPlan(
            allowed_tools=("search_product_tool", "get_product_description_tool"),
            preferred_tool="search_product_tool",
            tool_args_patch=args,
            forbidden_tools=("get_products_recommendations_tool",),
        )
    if frame.sub_intent == "recent_product_set_size_availability":
        return ToolPlan(
            forbidden_tools=(
                "search_product_tool",
                "get_product_description_tool",
                "get_products_recommendations_tool",
            ),
            metadata={"response_intent": "recent_product_set_size_availability"},
        )
    if frame.sub_intent == "recent_product_set_ranking":
        return ToolPlan(
            forbidden_tools=(
                "search_product_tool",
                "get_product_description_tool",
                "get_products_recommendations_tool",
            ),
            metadata={
                "response_intent": "recent_product_set_ranking",
                "metric": entities.get("recent_product_set_metric"),
                "direction": entities.get("recent_product_set_direction"),
            },
        )
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
    if frame.sub_intent == "benefit_event_list_lookup":
        return ToolPlan(
            allowed_tools=("get_benefit_event_deal_list_tool",),
            preferred_tool="get_benefit_event_deal_list_tool",
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
    if frame.sub_intent in {
        "product_event_lookup",
        "product_deal_lookup",
        "product_coupon_lookup",
        "product_benefit_lookup",
    }:
        product_names = entities.get("product_names") or ()
        args: dict[str, Any] = {}
        if product_names:
            args["keyword"] = product_names[0]
        if entities.get("brand_cd"):
            args["brand_cd"] = entities["brand_cd"]
        if entities.get("tire_size"):
            args["size"] = entities["tire_size"]
        return ToolPlan(
            allowed_tools=(
                "search_product_tool",
                "get_product_applicable_events_tool",
                "get_product_promotions_tool",
                "get_events_tool",
                "get_deals_tool",
            ),
            preferred_tool="search_product_tool",
            tool_args_patch=args,
            forbidden_tools=(
                "get_products_recommendations_tool",
                "get_product_description_tool",
                "quick_order_tool",
                "transaction_store_preview_tool",
                "get_store_schedule_tool",
            ),
            metadata={
                "response_intent": frame.sub_intent,
                "goal_type": "product_event_lookup",
                "benefit_lookup_type": entities.get("product_benefit_lookup_type"),
            },
        )
    if frame.sub_intent == "best_seller_search":
        args: dict[str, Any] = {"limit": 5}
        for key in ("vehicle_query", "months", "from_date", "to_date"):
            value = entities.get(key)
            if value not in (None, "", (), []):
                args[key] = value
        return ToolPlan(
            allowed_tools=("get_best_selling_products_tool",),
            preferred_tool="get_best_selling_products_tool",
            tool_args_patch=args,
            forbidden_tools=("get_products_recommendations_tool",),
        )
    if frame.intent == "product_search":
        product_names = entities.get("product_names") or ()
        if (
            len(product_names) >= 2
            and not entities.get("multi_product_detail_request")
            and frame.sub_intent == "product_name_search"
        ):
            return ToolPlan(
                forbidden_tools=(
                    "search_product_tool",
                    "get_product_description_tool",
                    "get_products_recommendations_tool",
                ),
                metadata={"response_intent": "multi_product_intent_clarification"},
            )
        keyword = entities.get("product_keyword") or (entities.get("product_names") or ("",))[0]
        args = {"keyword": keyword}
        if entities.get("tire_size"):
            args["size"] = entities["tire_size"]
        if entities.get("brand_cd"):
            args["brand_cd"] = entities["brand_cd"]
        is_multi_product_search = len(product_names) >= 2 and bool(entities.get("multi_product_detail_request"))
        return ToolPlan(
            allowed_tools=(
                ("search_product_tool", "get_product_description_tool")
                if is_multi_product_search
                else ("search_product_tool",)
            ),
            preferred_tool="search_product_tool",
            tool_args_patch=args,
            forbidden_tools=("get_products_recommendations_tool",),
            metadata={"response_intent": "multi_product_detail"} if is_multi_product_search else {},
        )
    if frame.sub_intent == "product_attribute_lookup":
        args = {"keyword": (entities.get("product_names") or ("",))[0]}
        if entities.get("brand_cd"):
            args["brand_cd"] = entities["brand_cd"]
        if not tire_size:
            return ToolPlan(
                allowed_tools=("search_product_summary_tool",),
                preferred_tool="search_product_summary_tool",
                tool_args_patch=args,
                forbidden_tools=("get_products_recommendations_tool", "generic_unsized_recommendation"),
            )
        args["size"] = tire_size
        return ToolPlan(
            allowed_tools=("search_product_tool",),
            preferred_tool="search_product_tool",
            tool_args_patch=args,
            forbidden_tools=("get_products_recommendations_tool", "generic_unsized_recommendation"),
        )
    if frame.sub_intent == "product_attribute_explanation" and entities.get("requested_product_attribute") == "car_type":
        return ToolPlan(
            forbidden_tools=("get_products_recommendations_tool",),
            metadata={
                "response_intent": "product_attribute_explanation",
                "requested_product_attribute": "car_type",
            },
        )
    if frame.intent == "product_description":
        product_names = entities.get("product_names") or ()
        args = {"keyword": (product_names or ("",))[0]}
        if entities.get("brand_cd"):
            args["brand_cd"] = entities["brand_cd"]
        if not tire_size:
            if len(product_names) >= 2:
                return ToolPlan(
                    allowed_tools=("search_product_summary_tool",),
                    preferred_tool="search_product_summary_tool",
                    forbidden_tools=("get_products_recommendations_tool", "search_product_tool"),
                    metadata={"response_intent": "multi_product_detail"},
                )
            return ToolPlan(
                allowed_tools=("search_product_summary_tool",),
                preferred_tool="search_product_summary_tool",
                tool_args_patch=args,
                forbidden_tools=("get_products_recommendations_tool", "search_product_tool"),
            )
        if len(product_names) >= 2:
            return ToolPlan(
                allowed_tools=("search_product_tool",),
                preferred_tool="search_product_tool",
                forbidden_tools=("get_products_recommendations_tool",),
                metadata={"response_intent": "multi_product_detail"},
            )
        args["size"] = tire_size
        return ToolPlan(
            allowed_tools=("search_product_tool", "get_product_description_tool"),
            preferred_tool="search_product_tool",
            tool_args_patch=args,
            forbidden_tools=("get_products_recommendations_tool",),
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
                allowed_tools=("search_product_tool", "get_product_description_tool", "get_cheapest_price_tool"),
                preferred_tool="search_product_tool",
                tool_args_patch=args,
                forbidden_tools=("get_products_recommendations_tool", "product_card_first_response"),
            )
        product_names = entities.get("product_names") or ()
        if not tire_size and product_names:
            summary_args = {"keyword": product_names[0]}
            if entities.get("brand_cd"):
                summary_args["brand_cd"] = entities["brand_cd"]
            is_multi_product_summary = len(product_names) >= 2
            return ToolPlan(
                allowed_tools=("search_product_summary_tool", "get_product_description_tool"),
                preferred_tool="search_product_summary_tool",
                tool_args_patch={} if is_multi_product_summary else summary_args,
                forbidden_tools=(
                    "get_products_recommendations_tool",
                    "product_card_first_response",
                    "search_product_tool",
                ),
                metadata={"response_intent": "multi_product_detail"} if is_multi_product_summary else {},
            )
        return ToolPlan(
            allowed_tools=("search_product_tool", "get_product_description_tool", "get_cheapest_price_tool"),
            preferred_tool="search_product_tool",
            tool_args_patch=args,
            forbidden_tools=("get_products_recommendations_tool", "product_card_first_response"),
        )
    if frame.intent == "product_search":
        product_names = entities.get("product_names") or ()
        product_families = entities.get("product_family_names") or ()
        keyword = (
            entities.get("product_keyword")
            or (product_names[0] if product_names else None)
            or (product_families[0] if product_families else "")
        )
        args = {"keyword": keyword, "limit": 10}
        if entities.get("tire_size"):
            args["size"] = entities["tire_size"]
        if entities.get("brand_cd"):
            args["brand_cd"] = entities["brand_cd"]
        is_multi_product_search = len(product_names) >= 2
        return ToolPlan(
            allowed_tools=(
                ("search_product_tool", "get_product_description_tool")
                if is_multi_product_search
                else ("search_product_tool",)
            ),
            preferred_tool="search_product_tool",
            tool_args_patch=args,
            forbidden_tools=("get_products_recommendations_tool",),
            metadata={
                "response_intent": "multi_product_detail" if is_multi_product_search else frame.sub_intent or "product_search",
                **({"product_family_names": product_families} if product_families else {}),
            },
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
    args = dict(entities.get("recommendation_scenario_tool_args_patch") or {})
    if entities.get("general_tire_preference") == "non_ev":
        args["rcmd_type"] = "tstation"
        args["suppress_vehicle_type_filter"] = True
        args["suppress_season_filter"] = True
    if entities.get("vehicle_category"):
        if entities.get("general_tire_preference") != "non_ev":
            args.setdefault("vehicle_type", entities["vehicle_category"])
    if entities.get("quiet_focus") and "rcmd_type" not in args:
        args["rcmd_type"] = "low_vibration"
    elif entities.get("value_focus") and "rcmd_type" not in args:
        args["rcmd_type"] = "value"
    elif entities.get("recommendation_metric") == "fuel_efficiency" and "rcmd_type" not in args:
        args["rcmd_type"] = "fuel_efficiency"
    elif entities.get("performance") == "performance" and "rcmd_type" not in args:
        args["rcmd_type"] = "performance"
    if entities.get("season") == "winter" and not args.get("season_nm"):
        if args.get("rcmd_type"):
            args["season_nm"] = "겨울"
        else:
            args.update({"rcmd_type": "snow", "season_nm": "겨울"})
    elif entities.get("season") == "all_weather" and not args.get("season_nm"):
        if args.get("rcmd_type"):
            args["season_nm"] = "올웨더"
        else:
            args.update({"rcmd_type": "all_weather", "season_nm": "올웨더"})
    elif entities.get("season") == "all_season" and not args.get("season_nm"):
        if args.get("rcmd_type"):
            args["season_nm"] = "사계절"
        else:
            args.update({"rcmd_type": "all_weather", "season_nm": "사계절"})
    elif entities.get("season") == "summer" and not args.get("season_nm"):
        args["season_nm"] = "여름"
    if entities.get("general_tire_preference") == "non_ev":
        args.pop("season_nm", None)
    if entities.get("explicit_tire_size") or entities.get("price_goal") != "similar_range":
        if entities.get("tire_size"):
            args["tire_size"] = entities["tire_size"]
    if entities.get("price_goal") == "lowest":
        args["sort_by"] = "price_asc"
    for key in ("min_price", "max_price"):
        if entities.get(key) is not None:
            args[key] = entities[key]
    if entities.get("brand_cd"):
        args["brand_cd"] = entities["brand_cd"]
        if frame.intent == "product_recommendation":
            args["allow_cross_brand_fill"] = False
    if entities.get("general_tire_preference") == "non_ev":
        args.pop("vehicle_type", None)
    if "rcmd_type" not in args and not any(
        args.get(key) not in (None, "", [], {})
        for key in ("vehicle_type", "season_nm", "pfm_nm", "prc_grd", "sort_by")
    ):
        args["rcmd_type"] = "tstation"
    allowed_tools = ("get_products_recommendations_tool",)
    required_slots: tuple[str, ...] = ()
    metadata: dict[str, Any] = {
        key: entities[key]
        for key in (
            "recommendation_scenario",
            "recommendation_scenario_label",
            "applied_rcmd_type",
            "applied_vehicle_type",
            "applied_season_nm",
            "approximation",
            "approximation_basis",
        )
        if key in entities
    }
    expected_tool_args = _recommendation_expected_tool_args(args)
    if expected_tool_args:
        metadata["recommendation_expected_tool_args"] = expected_tool_args
    if metadata:
        metadata.setdefault("response_intent", "catalog_recommendation")
        metadata.setdefault(
            "forbidden_behaviors",
            (
                "drop_recommendation_scenario",
                "claim_unsupported_scenario_as_exact",
            ),
        )
    if entities.get("discovery_followup_action") == "vehicle_resolved_recommendation":
        metadata = {
            **metadata,
            "response_intent": "vehicle_resolved_recommendation",
            "flow_step": "select_vehicle",
        }
        if entities.get("named_registered_vehicle_anchor"):
            metadata["named_registered_vehicle_anchor"] = entities["named_registered_vehicle_anchor"]
            metadata["flow_step"] = "resolve_named_vehicle"
            return ToolPlan(
                allowed_tools=("get_my_cars_tool", "get_products_recommendations_tool"),
                preferred_tool="get_my_cars_tool",
                tool_args_patch=args,
                metadata=metadata,
            )
        return ToolPlan(
            allowed_tools=("get_my_cars_tool",),
            preferred_tool="get_my_cars_tool",
            tool_args_patch={},
            forbidden_tools=("get_products_recommendations_tool",),
            metadata=metadata,
        )
    if entities.get("discovery_followup_action") == "vehicle_based_recommendation_refinement":
        allowed_tools = ("get_my_cars_tool", "get_products_recommendations_tool")
        required_slots = ("tire_size",)
        metadata = {**metadata, "response_intent": entities["discovery_followup_action"]}
    return ToolPlan(
        allowed_tools=allowed_tools,
        preferred_tool="get_products_recommendations_tool",
        tool_args_patch=args,
        required_slots=required_slots,
        metadata=metadata,
    )
