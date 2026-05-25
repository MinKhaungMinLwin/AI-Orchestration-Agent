"""Shared policy helpers for store special-service and review-detail requests."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


StoreServiceIntent = Literal[
    "store_special_service",
    "store_review_detail",
    "store_rating_summary",
    "none",
]


class StoreServiceGateDecision(BaseModel):
    intent: StoreServiceIntent = Field(description="Classified store service/review intent.")
    needs_store_detail_cta: bool = Field(description="Whether response should include store detail CTA when possible.")
    needs_unverifiable_guidance: bool = Field(
        description="Whether requested store condition is not directly verifiable from store search data."
    )
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
STORE_REVIEW_UNAVAILABLE_TEXT_RE = re.compile(
    r"(?:리뷰|후기)\s*(?:상세\s*)?(?:내용은?\s*)?(?:현재\s*)?(?:조회\s*가능한\s*)?정보에\s*포함되어\s*있지\s*않아요\.?",
    re.IGNORECASE,
)

_UNVERIFIABLE_STORE_PREFERENCE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"리프트|대형\s*리프트|차량용\s*리프트", re.IGNORECASE), "리프트 보유 여부"),
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


def unverifiable_store_preference_labels(text: str) -> list[str]:
    if not text:
        return []
    labels: list[str] = []
    for pattern, label in _UNVERIFIABLE_STORE_PREFERENCE_RULES:
        if pattern.search(text) and label not in labels:
            labels.append(label)
    return labels


def is_store_contact_redirect_text(text: str) -> bool:
    return bool(STORE_CONTACT_REDIRECT_RE.search(text or ""))


def is_store_detail_page_cta_text(text: str) -> bool:
    return bool(STORE_DETAIL_PAGE_CTA_RE.search(text or ""))


def is_store_review_detail_request(text: str) -> bool:
    value = text or ""
    if STORE_REVIEW_WRITE_RE.search(value):
        return False
    return bool(STORE_REVIEW_DETAIL_USER_RE.search(value))


def replace_store_review_unavailable_text(text: str, replacement: str) -> str:
    return STORE_REVIEW_UNAVAILABLE_TEXT_RE.sub(replacement, text or "").strip()


def decide_store_service_gate(*, user_text: str = "", assistant_text: str = "") -> StoreServiceGateDecision:
    """Classify store special-service/review-detail handling needs without an LLM call."""
    text = user_text or ""
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
