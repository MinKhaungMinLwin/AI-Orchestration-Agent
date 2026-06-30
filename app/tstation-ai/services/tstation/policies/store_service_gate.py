"""Shared policy helpers for store special-service and review-detail requests."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


StoreServiceIntent = Literal[
    "store_attribute_inquiry",
    "store_special_service",
    "store_review_detail",
    "store_rating_summary",
    "store_visual_detail",
    "none",
]


class StoreServiceGateDecision(BaseModel):
    intent: StoreServiceIntent = Field(description="Classified store service/review intent.")
    needs_store_detail_cta: bool = Field(description="Whether response should include store detail CTA when possible.")
    needs_unverifiable_guidance: bool = Field(
        description="Whether requested store condition is not directly verifiable from store search data."
    )
    reason: str = Field(description="Short English reason for traces/logs only.")


STORE_ATTRIBUTE_TYPE = Literal["service", "equipment", "operating_condition", "subjective_quality", "unknown"]
STORE_ATTRIBUTE_VERIFICATION_LEVEL = Literal[
    "tool_verifiable",
    "store_contact_required",
    "unsupported_or_policy",
]
STORE_NAME_ROLE = Literal["target", "context", "none"]


STORE_SERVICE_CATALOG: dict[str, dict[str, object]] = {
    "tire_storage": {
        "name": "타이어 보관서비스",
        "codes": ("119",),
        "patterns": (
            re.compile(r"보관\s*서비스|타이어\s*보관|타이어\s*호텔|윈터\s*타이어|겨울\s*타이어", re.IGNORECASE),
        ),
    },
    "wheel_alignment": {
        "name": "휠얼라인먼트",
        "codes": ("124", "125"),
        "patterns": (re.compile(r"휠\s*얼라이먼트|휠\s*얼라인먼트|얼라인먼트", re.IGNORECASE),),
    },
    "maintenance": {
        "name": "경정비",
        "codes": ("121", "122"),
        "patterns": (
            re.compile(r"경정비|엔진\s*오일|엔진오일|실내\s*필터|에어컨\s*필터|필터|와이퍼", re.IGNORECASE),
        ),
    },
    "free_check": {
        "name": "무상점검",
        "codes": ("126",),
        "patterns": (re.compile(r"무상\s*점검|무료\s*점검|all\s*my\s*t|올마이티", re.IGNORECASE),),
    },
    "imported_tire": {
        "name": "수입타이어 취급",
        "codes": ("120",),
        "patterns": (re.compile(r"수입\s*타이어", re.IGNORECASE),),
    },
}


def normalize_store_service_request(text: str) -> dict[str, object] | None:
    """Return a validated service catalog match for store service search/inquiry."""
    value = text or ""
    for service_key, service in STORE_SERVICE_CATALOG.items():
        patterns = service.get("patterns") or ()
        if any(pattern.search(value) for pattern in patterns if isinstance(pattern, re.Pattern)):
            return {
                "service_key": service_key,
                "service_name": str(service["name"]),
                "service_codes": tuple(str(code) for code in service["codes"]),
            }
    return None


class StoreAttributeInquiry(BaseModel):
    store_name: str = Field(default="", description="Current or carried store name, if available.")
    attribute_text: str = Field(default="", description="Raw store attribute/service/equipment phrase from user text.")
    attribute_type: STORE_ATTRIBUTE_TYPE = Field(default="unknown", description="Structured attribute family.")
    verification_level: STORE_ATTRIBUTE_VERIFICATION_LEVEL = Field(
        default="store_contact_required",
        description="Whether the attribute can be answered from tool data or requires direct store contact.",
    )


class StoreNameRoleDecision(BaseModel):
    role: STORE_NAME_ROLE = Field(description="Whether the current-turn store name is an action target or context.")
    store_name: str = Field(default="", description="Extracted current-turn store name, if any.")
    reason: str = Field(description="Short English reason for traces/logs only.")


STORE_CONTACT_REDIRECT_RE = re.compile(
    r"매장(?:\s*직원)?(?:으로|에|에게)?\s*(?:직접\s*)?(?:문의|확인)(?:해\s*주세요|하시면|하세요|하면)",
    re.IGNORECASE,
)
STORE_DETAIL_PAGE_CTA_RE = re.compile(
    r"(?:상세\s*)?(?:리뷰|후기).{0,40}매장\s*상세\s*페이지|매장\s*상세\s*페이지.{0,40}(?:상세\s*)?(?:리뷰|후기)",
    re.IGNORECASE,
)
STORE_REVIEW_DETAIL_USER_RE = re.compile(
    r"(?:매장\s*)?(?:상세\s*)?(?:리뷰|후기)(?:\s*(?:상세|내용))?\s*(?:확인|조회|보여|알려|있어|궁금|봐|볼래|줘|해줘)|"
    r"(?:상세\s*)?(?:리뷰|후기)\s*(?:내용|상세)|"
    r"(?:매장\s*)?(?:리뷰|후기)(?:는|가)?\s*(?:어때|어떠|어떤|괜찮)",
    re.IGNORECASE,
)
STORE_REVIEW_WRITE_RE = re.compile(r"(?:리뷰|후기).{0,12}(?:작성|쓰기|써|남기|등록|수정|삭제)", re.IGNORECASE)
STORE_RATING_SUMMARY_RE = re.compile(r"(?:매장\s*)?(?:평점|별점|평가)(?:는|가)?\s*(?:어때|어떠|얼마|몇|높|좋|괜찮)", re.IGNORECASE)
STORE_VISUAL_DETAIL_USER_RE = re.compile(
    r"(?:매장\s*)?(?:전경|사진|외관|내부\s*사진|내부|모습|이미지|매장\s*사진)"
    r".{0,20}(?:보고|보여|볼\s*수|있어|확인|궁금|줘|싶)|"
    r"(?:보고|보여|확인).{0,20}(?:매장\s*)?(?:전경|사진|외관|내부\s*사진|내부|모습|이미지)",
    re.IGNORECASE,
)
STORE_REVIEW_UNAVAILABLE_TEXT_RE = re.compile(
    r"(?:리뷰|후기)\s*(?:상세\s*)?(?:내용은?\s*)?(?:현재\s*)?(?:조회\s*가능한\s*)?정보에\s*포함되어\s*있지\s*않아요\.?",
    re.IGNORECASE,
)

_UNVERIFIABLE_STORE_PREFERENCE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"보관\s*서비스|타이어\s*보관|윈터\s*타이어\s*보관|겨울\s*타이어\s*보관|"
            r"보관\s*(?:돼|되|가능|해\s*줘|되나요|가능해)",
            re.IGNORECASE,
        ),
        "타이어 보관 서비스 운영 여부",
    ),
    (
        re.compile(r"세차(?:\s*서비스)?|손세차|자동세차", re.IGNORECASE),
        "세차 서비스 운영 여부",
    ),
    (
        re.compile(r"튜닝(?:\s*서비스)?|광택|썬팅|디테일링|랩핑|유리막|언더코팅|블랙박스", re.IGNORECASE),
        "튜닝/부가 서비스 운영 여부",
    ),
    (re.compile(r"리프트|대형\s*리프트|차량용\s*리프트", re.IGNORECASE), "리프트 보유 여부"),
    (
        re.compile(
            r"(?=.*(?:야간|심야|퇴근\s*후|퇴근후|저녁|늦게))"
            r"(?=.*(?:정비|작업|서비스|문\s*여|문여|영업\s*하|영업하|운영\s*하|운영하))",
            re.IGNORECASE,
        ),
        "야간정비 운영 여부",
    ),
    (re.compile(r"질소\s*충전|질소", re.IGNORECASE), "질소 충전 여부"),
    (re.compile(r"대기\s*공간|대기실|라운지|휴게실|대기\s*환경", re.IGNORECASE), "대기 공간"),
    (re.compile(r"워셔액\s*(?:무료|제공|보충)?|워셔액", re.IGNORECASE), "워셔액 무료 제공"),
    (
        re.compile(
            r"여성\s*(?:전용|친화|편의|운전자|방문|고객|주차)|여성이\s*방문|"
            r"파우더룸|수유실|탈의실|여성\s*주차\s*구역",
            re.IGNORECASE,
        ),
        "여성 방문 편의/만족도",
    ),
    (re.compile(r"키즈|아이\s*동반|놀이방", re.IGNORECASE), "키즈/가족 편의시설"),
    (re.compile(r"발렛|매장\s*픽업|픽업\s*가능|딜리버리", re.IGNORECASE), "발렛/픽업 같은 부가 서비스"),
    (re.compile(r"음료|커피|간식|무료\s*음료|마실\s*것", re.IGNORECASE), "음료 제공"),
    (re.compile(r"청결|깨끗|분위기|쾌적|시설\s*상태", re.IGNORECASE), "매장 분위기/청결"),
    (re.compile(r"사은품|기념품|추가\s*서비스\s*무료|무료\s*서비스", re.IGNORECASE), "사은품/추가 무료 서비스"),
    (
        re.compile(r"(?:얼라인먼트|휠\s*얼라이먼트|밸런스).{0,12}(?:숙련도|실력|정확도|꼼꼼)", re.IGNORECASE),
        "얼라인먼트/밸런스 숙련도",
    ),
    (re.compile(r"숙련도|실력|잘\s*보는|잘하는|정확도|꼼꼼", re.IGNORECASE), "작업 숙련도"),
)
_STORE_SERVICE_AVAILABILITY_SIGNAL_RE = re.compile(
    r"보관\s*서비스|타이어\s*보관|윈터\s*타이어\s*보관|겨울\s*타이어\s*보관|"
    r"보관\s*(?:돼|되|가능|되나요|가능해)|질소\s*충전|질소|"
    r"(?=.*(?:야간|심야|퇴근\s*후|퇴근후|저녁|늦게))(?=.*(?:정비|작업|서비스|문\s*여|문여|영업\s*하|영업하|운영\s*하|운영하))|"
    r"얼라인먼트.{0,12}(?:잘|무료|가능)",
    re.IGNORECASE,
)
_STORE_NAME_RE = re.compile(r"((?:티스테이션\s*)?[가-힣A-Za-z0-9]+(?:점|매장))")
_STORE_MENTION_CONTEXT_RE = re.compile(
    r"티스테이션|더타이어샵|매장|지점|장착점|주소|전화|연락처|영업|운영|휴무|"
    r"예약|재고|입고|장착|교체|작업|확인|구매|주문|질소|보관|야간|심야|퇴근\s*후|퇴근후|저녁|늦게|"
    r"얼라인먼트|휠\s*얼라이먼트|리프트|공휴일|휴일|일요일|토요일|문\s*열",
    re.IGNORECASE,
)
_BARE_STORE_NAME_TURN_RE = re.compile(r"^\s*(?:티스테이션\s*)?[가-힣A-Za-z0-9]+(?:점|매장)\s*$", re.IGNORECASE)
_ATTRIBUTE_QUESTION_RE = re.compile(
    r"가능\s*해|가능한가|가능(?:하|한)|가능(?:\s*[?!.]|$)|돼|되(?:나|나요|니|냐)?|있어|있나|있나요|"
    r"해\s*줘|해줘|운영\s*해|운영해|영업\s*하|영업하|문\s*여|문여|잘\s*(?:봐|보|하)",
    re.IGNORECASE,
)
_TRANSACTION_ACTION_REQUEST_RE = re.compile(
    r"주문\s*해\s*줘|주문해줘|구매\s*해\s*줘|구매해줘|결제|장바구니|카트|"
    r"살래|살게|사고\s*싶|사려고|구매\s*할래|주문\s*할래",
    re.IGNORECASE,
)
_TRANSACTION_OBJECT_ANCHOR_RE = re.compile(
    r"\d+\s*개|"
    r"\d{3}\s*/?\s*\d{2}\s*R?\s*\d{2}|"
    r"Kinergy|Ventus|Dynapro|Optimo|Laufenn|iON|"
    r"키너지|벤투스|다이나프로|옵티모|아이온|라우펜|타이어",
    re.IGNORECASE,
)
_ADJACENT_NON_ATTRIBUTE_RE = re.compile(
    r"내\s*차\s*정비\s*(?:일정|시기)|정비\s*이력|정비이력|정비\s*내역|정비내역|"
    r"주문한\s*거.{0,20}(?:장착|예약)\s*가능|예약\s*(?:조회|내역|확인|상태)|"
    r"예약\s*(?:가능|가능한\s*(?:시간|일정|슬롯)|잡|해|걸|보여|알려)|방문예약|"
    r"타이어\s*(?:교체|장착).{0,12}예약|장착\s*가능|다시\s*확인|"
    r"점심\s*시간|그냥\s*가도|대기\s*시간|한가|붐비|혼잡",
    re.IGNORECASE,
)
_ATTRIBUTE_SUFFIX_RE = re.compile(
    r"(?:도|은|는|이|가|을|를)?\s*"
    r"(?:가능\s*해|가능한가|가능(?:하|한)|가능(?:\s*[?!.]|$)|돼|되(?:나|나요|니|냐)?|있어|있나|있나요|"
    r"해\s*줘|해줘|운영\s*해|운영해|영업\s*하|영업하|문\s*여|문여|잘\s*(?:봐|보|하)).*$",
    re.IGNORECASE,
)
_ATTRIBUTE_STOPWORDS_RE = re.compile(
    r"^(?:티스테이션|더타이어샵|그리고|혹시|그럼|거기|해당\s*매장|매장|지점)\s*",
    re.IGNORECASE,
)
_SERVICE_RESERVATION_TAIL_RE = re.compile(
    r"(?:도\s*하는\s*것\s*같은데|도\s*하나|도\s*해줘|도\s*돼|도\s*되나|"
    r"예약(?:은|은요|은 어디서|은 어떻게)?|어디서\s*해|어떻게\s*해|문의(?:는|는요)?|확인(?:은|은요)?)"
    r".*$",
    re.IGNORECASE,
)
_TOOL_VERIFIABLE_ATTRIBUTE_RE = re.compile(r"주소|전화|전화번호|연락처|영업\s*시간|운영\s*시간|휴무|위치", re.IGNORECASE)
_EQUIPMENT_ATTRIBUTE_RE = re.compile(r"리프트|대형\s*리프트|차량용\s*리프트|장비|설비", re.IGNORECASE)
_OPERATING_CONDITION_ATTRIBUTE_RE = re.compile(
    r"야간|심야|퇴근\s*후|퇴근후|저녁|늦게|주말|공휴일|휴일|일요일|토요일|운영|영업|문\s*열|문\s*여",
    re.IGNORECASE,
)
_SUBJECTIVE_QUALITY_ATTRIBUTE_RE = re.compile(r"잘\s*(?:봐|보|하)|숙련도|실력|정확도|꼼꼼|친절|평가|평점", re.IGNORECASE)
_WARRANTY_OR_COMPLAINT_CONTEXT_RE = re.compile(
    r"보증|워런티|warranty|품질\s*보증|안심\s*서비스|안심서비스|클레임|불만|하자|불량|문제|"
    r"마모|편마모|수명|보상|무상\s*(?:교체|교환)|환불|책임|광고(?:랑|와)?\s*다르",
    re.IGNORECASE,
)
_STORE_TARGET_ACTION_RE = re.compile(
    r"영업|운영|휴무|문\s*열|주소|위치|전화|연락처|정보|상세|사진|외관|내부|리뷰|후기|"
    r"평점|평가|예약|재고|장착|교체|작업|가능|돼|되나|있어|보관|질소|얼라인먼트|리프트|"
    r"야간|심야|퇴근\s*후|퇴근후|저녁|늦게|문\s*여|문여|대기실|대기\s*공간",
    re.IGNORECASE,
)
_STORE_CONTEXT_MARKER_RE = re.compile(
    r"에서\s*(?:교체|장착|구매|주문|방문|서비스|정비|받|했|한|산)|"
    r"(?:교체|장착|구매|주문|방문|서비스|정비).{0,12}(?:했던|한|받은)\s*(?:매장|지점|곳)",
    re.IGNORECASE,
)


def _normalize_store_name(value: str | None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return re.sub(r"^(?:티스테이션|더타이어샵)\s*", "", text, flags=re.IGNORECASE).strip()


def has_valid_store_mention_context(text: str) -> bool:
    """Return True when suffix-style store extraction is supported by store context."""
    value = text or ""
    return bool(_BARE_STORE_NAME_TURN_RE.fullmatch(value) or _STORE_MENTION_CONTEXT_RE.search(value))


def extract_valid_store_name(text: str) -> str | None:
    """Extract a store name only when the surrounding text makes it a store mention."""
    value = text or ""
    if not has_valid_store_mention_context(value):
        return None
    for match in _STORE_NAME_RE.finditer(value):
        candidate = re.sub(r"\s+", " ", match.group(1)).strip()
        normalized = _normalize_store_name(candidate)
        if normalized in {"장착점", "지점"}:
            continue
        return candidate
    return None


def classify_store_name_role(text: str, *, store_name: str | None = None) -> StoreNameRoleDecision:
    """Classify whether a store mention is the current action target or background context."""
    value = str(text or "")
    extracted_store_name = _normalize_store_name(store_name) or _normalize_store_name(extract_valid_store_name(value))
    if not extracted_store_name:
        return StoreNameRoleDecision(role="none", reason="No valid current-turn store name.")

    if _WARRANTY_OR_COMPLAINT_CONTEXT_RE.search(value) and _STORE_CONTEXT_MARKER_RE.search(value):
        return StoreNameRoleDecision(
            role="context",
            store_name=extracted_store_name,
            reason="Store mention describes prior service context for support/warranty complaint.",
        )
    if extract_store_attribute_inquiry(value, store_name=extracted_store_name) is not None:
        return StoreNameRoleDecision(
            role="target",
            store_name=extracted_store_name,
            reason="Store mention is the explicit target of an attribute/service question.",
        )
    if _STORE_TARGET_ACTION_RE.search(value) and not _WARRANTY_OR_COMPLAINT_CONTEXT_RE.search(value):
        return StoreNameRoleDecision(
            role="target",
            store_name=extracted_store_name,
            reason="Store mention is tied to a store lookup, booking, or attribute action.",
        )
    if _STORE_CONTEXT_MARKER_RE.search(value):
        return StoreNameRoleDecision(
            role="context",
            store_name=extracted_store_name,
            reason="Store mention is background information, not the current action target.",
        )
    return StoreNameRoleDecision(
        role="target",
        store_name=extracted_store_name,
        reason="Bare or direct store mention defaults to target for store information lookup.",
    )


def extract_store_attribute_inquiry(
    text: str,
    *,
    store_name: str | None = None,
) -> StoreAttributeInquiry | None:
    """Extract a generic store attribute inquiry while preserving raw attribute text."""
    value = str(text or "").strip()
    if not value or not _ATTRIBUTE_QUESTION_RE.search(value):
        return None
    if _WARRANTY_OR_COMPLAINT_CONTEXT_RE.search(value) and _STORE_CONTEXT_MARKER_RE.search(value):
        return None
    store_label = _normalize_store_name(store_name)
    if not store_label:
        extracted_store_name = extract_valid_store_name(value)
        if extracted_store_name:
            store_label = _normalize_store_name(extracted_store_name)
    if not store_label:
        return None
    labels = unverifiable_store_preference_labels(value)
    if (
        not labels
        and _TRANSACTION_ACTION_REQUEST_RE.search(value)
        and _TRANSACTION_OBJECT_ANCHOR_RE.search(value)
    ):
        return None
    adjacent_non_attribute = _ADJACENT_NON_ATTRIBUTE_RE.search(value)
    if adjacent_non_attribute and not labels:
        return None

    working = value
    if store_label:
        working = re.sub(rf"(?:티스테이션\s*)?{re.escape(store_label)}", " ", working, count=1, flags=re.IGNORECASE)
    if labels:
        working = _SERVICE_RESERVATION_TAIL_RE.sub("", working).strip()
    working = _ATTRIBUTE_SUFFIX_RE.sub("", working).strip()
    working = _ATTRIBUTE_STOPWORDS_RE.sub("", working).strip()
    working = re.sub(r"^(?:에서|에|도|은|는|이|가|을|를|혹시)\s*", "", working).strip()
    working = re.sub(r"\s+", " ", working).strip(" ?!.")
    attribute_text = working or (labels[0] if labels else "")
    if not attribute_text:
        return None

    attr_type: STORE_ATTRIBUTE_TYPE = "unknown"
    verification_level: STORE_ATTRIBUTE_VERIFICATION_LEVEL = "store_contact_required"
    if _TOOL_VERIFIABLE_ATTRIBUTE_RE.search(attribute_text):
        attr_type = "operating_condition"
        verification_level = "tool_verifiable"
    elif _EQUIPMENT_ATTRIBUTE_RE.search(attribute_text):
        attr_type = "equipment"
    elif _OPERATING_CONDITION_ATTRIBUTE_RE.search(attribute_text):
        attr_type = "operating_condition"
    elif _SUBJECTIVE_QUALITY_ATTRIBUTE_RE.search(attribute_text):
        attr_type = "subjective_quality"
        verification_level = "unsupported_or_policy"
    elif labels:
        attr_type = "service"

    return StoreAttributeInquiry(
        store_name=store_label,
        attribute_text=attribute_text,
        attribute_type=attr_type,
        verification_level=verification_level,
    )



def unverifiable_store_preference_labels(text: str) -> list[str]:
    if not text:
        return []
    labels: list[str] = []
    for pattern, label in _UNVERIFIABLE_STORE_PREFERENCE_RULES:
        if pattern.search(text) and label not in labels:
            labels.append(label)
    return labels


def has_store_service_availability_signal(text: str) -> bool:
    """Return True for store service availability anchors shared across policy layers."""
    return bool(_STORE_SERVICE_AVAILABILITY_SIGNAL_RE.search(text or ""))


def is_store_contact_redirect_text(text: str) -> bool:
    return bool(STORE_CONTACT_REDIRECT_RE.search(text or ""))


def is_store_detail_page_cta_text(text: str) -> bool:
    return bool(STORE_DETAIL_PAGE_CTA_RE.search(text or ""))


def is_store_review_detail_request(text: str) -> bool:
    value = text or ""
    if STORE_REVIEW_WRITE_RE.search(value):
        return False
    return bool(STORE_REVIEW_DETAIL_USER_RE.search(value))


def is_store_visual_detail_request(text: str) -> bool:
    return bool(STORE_VISUAL_DETAIL_USER_RE.search(text or ""))


def replace_store_review_unavailable_text(text: str, replacement: str) -> str:
    return STORE_REVIEW_UNAVAILABLE_TEXT_RE.sub(replacement, text or "").strip()


def decide_store_service_gate(*, user_text: str = "", assistant_text: str = "") -> StoreServiceGateDecision:
    """Classify store special-service/review-detail handling needs without an LLM call."""
    text = user_text or ""
    if extract_store_attribute_inquiry(text) is not None:
        return StoreServiceGateDecision(
            intent="store_attribute_inquiry",
            needs_store_detail_cta=True,
            needs_unverifiable_guidance=True,
            reason="User asks whether a specific store has a service/equipment/operating attribute.",
        )
    labels = unverifiable_store_preference_labels(text)
    if labels:
        return StoreServiceGateDecision(
            intent="store_special_service",
            needs_store_detail_cta=True,
            needs_unverifiable_guidance=True,
            reason="User asks about store capability not verifiable from store search data.",
        )
    if is_store_review_detail_request(text):
        return StoreServiceGateDecision(
            intent="store_review_detail",
            needs_store_detail_cta=True,
            needs_unverifiable_guidance=False,
            reason="User asks to inspect store review details.",
        )
    if is_store_visual_detail_request(text):
        return StoreServiceGateDecision(
            intent="store_visual_detail",
            needs_store_detail_cta=True,
            needs_unverifiable_guidance=False,
            reason="User asks to inspect store photos or visual details.",
        )
    if STORE_RATING_SUMMARY_RE.search(text):
        return StoreServiceGateDecision(
            intent="store_rating_summary",
            needs_store_detail_cta=False,
            needs_unverifiable_guidance=False,
            reason="User asks for store rating summary.",
        )
    if is_store_contact_redirect_text(assistant_text) or is_store_detail_page_cta_text(assistant_text):
        return StoreServiceGateDecision(
            intent="store_special_service",
            needs_store_detail_cta=True,
            needs_unverifiable_guidance=False,
            reason="Assistant directs user to store contact/detail page.",
        )
    return StoreServiceGateDecision(
        intent="none",
        needs_store_detail_cta=False,
        needs_unverifiable_guidance=False,
        reason="No store service/review-detail handling needed.",
    )
